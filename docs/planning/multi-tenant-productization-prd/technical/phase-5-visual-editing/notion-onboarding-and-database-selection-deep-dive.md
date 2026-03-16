# Notion Onboarding and Database Selection Deep Dive

## Objective

Define exactly how a user connects Notion, grants access, selects databases, and how that state is represented in the backend data model.

This deep dive answers:

- what the user experience should look like
- what users must do inside Notion (if anything)
- what schema/API/runtime changes are required from the current implementation

## Current State (As Implemented Today)

### UI and route surface

- `Connections` page exists and reads `GET /management/connections`.
- It is read-only right now (list + refresh only).
- There is no `Connect Notion` action and no OAuth redirect flow in the frontend.

### Backend management API

- `GET /management/connections` returns existing `connector_instances` rows for the authenticated owner.
- There are no endpoints for:
  - starting OAuth authorization
  - handling OAuth callback completion
  - listing available Notion databases for selection
  - creating/updating user-selected Notion targets from discovered databases

### Runtime credential model

- The app currently initializes a single global `NotionService` using `NOTION_API_KEY` from environment at startup.
- This means Notion auth is app-global, not user-connection scoped.
- `SchemaCache` currently relies on a static list of configured IDs and does not discover per-user data sources.

### Data model status

- Phase 4 includes `connector_instances`, `data_targets`, and `target_schema_snapshots`.
- `connector_instances` has `config`, `secret_ref`, `last_validated_at`, `last_error`, and `status`.
- There is no dedicated persistence model for OAuth handshake lifecycle (`state`, PKCE verifier, expiration, replay protection).
- There is no dedicated persistence model for OAuth token metadata lifecycle (refresh, expiry, revoke, rotated versions).
- There is no normalized store for discovered external Notion data sources to support selection UI.

## User Onboarding Flow (Target Experience)

### Step 1: User opens `Connections`

Show connector cards (Notion now, other providers later) with status:

- `Not connected`
- `Connected`
- `Action needed` (token expired/revoked/access lost)

Primary CTA on Notion card:

- `Connect Notion` when disconnected
- `Reconnect` when connection is unhealthy
- `Manage databases` when connected

### Step 2: User clicks `Connect Notion`

Frontend calls:

- `POST /management/connections/notion/oauth/start`

Backend response includes:

- `authorization_url` (Notion authorize URL with provider params + `state`)

Frontend performs top-level redirect.

### Step 3: User authorizes in Notion

User chooses workspace and approves integration capabilities.

### Step 4: OAuth callback completion

Notion redirects to backend callback endpoint:

- `GET /auth/callback/notion?code=...&state=...`

Backend:

- validates `state` and expiry
- exchanges `code` for tokens
- creates/updates owner-scoped `connector_instance` (`notion_oauth_workspace`)
- stores credential bundle securely (not plaintext in user-facing fields)
- marks connection `connected`
- redirects user back to UI (`/connections?connected=notion`)

### Step 5: Prompt for database access check

After returning to UI, show guided checklist:

1. Select databases to use in this app.
2. If a database is missing, add the integration in Notion database `...` menu under `Connections`.
3. Click `Refresh list`.

### Step 6: Select databases

Frontend fetches discovered sources:

- `GET /management/connections/{connection_id}/data-sources`

User can select one or more entries and click:

- `Use selected databases`

Backend creates/updates `data_targets` for those selections and runs schema sync for each target.

## What User Must Do In Notion

Notion OAuth authorization alone is usually not enough for a polished onboarding experience. Users should expect one Notion-side action when needed:

- If a specific database is not visible to the integration token, user must add/share that database with the integration in Notion (`Connections` in the database menu).

In-product messaging should make this explicit and include:

- a short "why this is needed" explanation
- a "Refresh databases" action after user grants access
- per-database error hints when permissions are missing

## Required Backend and Schema Changes

## 1) Keep using `connector_instances` as the connection anchor

`connector_instances` remains the top-level owner-scoped connection resource.

Recommended additions to `connector_instances`:

- `auth_status text not null default 'pending'`
  - values: `pending`, `connected`, `token_expired`, `revoked`, `error`
- `authorized_at timestamptz`
- `disconnected_at timestamptz`
- `provider_account_id text` (Notion workspace ID when available)
- `provider_account_name text` (workspace/bot label for UI)
- `last_synced_at timestamptz`
- `metadata jsonb not null default '{}'`

Rationale: keep dashboard status and lifecycle state queryable without dereferencing secret payload.

## 2) Add OAuth flow state table (anti-replay + expiry)

New table: `oauth_connection_states`

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `owner_user_id uuid not null references auth.users(id) on delete cascade`
- `provider text not null` (`notion`)
- `state_token_hash text not null unique`
- `pkce_verifier_encrypted text` (nullable if PKCE not used with Notion)
- `redirect_uri text not null`
- `expires_at timestamptz not null`
- `consumed_at timestamptz`
- `created_at timestamptz not null default now()`

RLS: owner-scoped policy (`owner_user_id = auth.uid()`).

## 3) Add secure credential lifecycle table

New table: `connector_credentials`

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `owner_user_id uuid not null references auth.users(id) on delete cascade`
- `connector_instance_id text not null`
- `provider text not null` (`notion`)
- `credential_type text not null` (`oauth2`)
- `secret_ref text not null` (pointer to secret backend entry)
- `token_expires_at timestamptz`
- `last_refreshed_at timestamptz`
- `revoked_at timestamptz`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`
- unique constraint on `(owner_user_id, connector_instance_id, provider, credential_type)`
- FK `(connector_instance_id, owner_user_id)` -> `connector_instances(id, owner_user_id)`

Important: do not store plaintext access/refresh tokens in list/read APIs.

## 4) Add discovered external sources table for selection UI

New table: `connector_external_sources`

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `owner_user_id uuid not null references auth.users(id) on delete cascade`
- `connector_instance_id text not null`
- `provider text not null` (`notion`)
- `external_source_id text not null` (Notion data source ID)
- `external_parent_id text` (optional parent database/page id)
- `display_name text not null`
- `is_accessible boolean not null default true`
- `last_seen_at timestamptz not null default now()`
- `last_sync_error text`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`
- unique `(owner_user_id, connector_instance_id, external_source_id)`
- FK `(connector_instance_id, owner_user_id)` -> `connector_instances(id, owner_user_id)`

This table supports:

- fast UI listing
- diffing newly discovered vs removed access
- permission troubleshooting without live Notion calls on every paint

## 5) Minor hardening for existing tables

- Add index on `data_targets(owner_user_id, connector_instance_id)`.
- Enforce that `data_targets.external_target_id` maps to a selected/discovered source for the same connection when provider is Notion.
- Keep RLS owner-scoping for all new tables.

## API Surface Additions

New endpoints:

- `POST /management/connections/notion/oauth/start`
  - create state row, return `authorization_url`
- `GET /auth/callback/notion`
  - validate state, exchange token, upsert connection + credential
- `POST /management/connections/{id}/refresh-sources`
  - call Notion with stored token, upsert `connector_external_sources`
- `GET /management/connections/{id}/data-sources`
  - list discovered sources + accessibility status
- `POST /management/connections/{id}/data-sources/select`
  - input: selected source ids
  - output: created/updated `data_targets`, sync results
- `POST /management/connections/{id}/disconnect`
  - revoke token if supported, mark disconnected/revoked

## Runtime Changes Required

- Replace global env-key-only Notion auth path with owner/connection-scoped credential resolution.
- Build `NotionClientFactory` (or equivalent) that constructs a Notion client per connection token.
- Update schema sync to load connection credential by `target.connector_instance_id` instead of relying on app-global key.
- Refactor `SchemaCache` keying from just `db_name` to owner+connection+source context.
- Keep bootstrap/dev fallback behavior explicit (feature flag) so production flow does not depend on hardcoded IDs.

## Data Model Mapping (Connection -> Target)

Recommended invariant:

1. One `connector_instance` represents one installed Notion workspace connection.
2. One or more selected Notion data sources map to one or more `data_targets`.
3. Each `data_target` references:
   - `connector_instance_id`
   - `external_target_id` (Notion data source id)
4. `target_schema_snapshots` remain the canonical schema history for each selected target.

## Security and Compliance Notes

- Keep token material outside user-readable list payloads.
- Store only a secret pointer (`secret_ref`) in primary business tables.
- Add audit events for:
  - OAuth start
  - OAuth success/failure
  - token refresh
  - source refresh
  - disconnect/revoke
- Ensure connection list APIs return status metadata, never credential payloads.

## Proposed Implementation Sequence

1. Add migrations for state, credentials, external source cache, and connector status metadata.
2. Add OAuth start/callback endpoints.
3. Add source discovery endpoints (`refresh-sources`, `list`).
4. Add source selection endpoint that creates/updates `data_targets`.
5. Update Connections UI:
   - Notion card with Connect/Reconnect
   - data source table with select + refresh
6. Refactor runtime credential resolution and schema sync to per-connection tokens.
7. Add integration tests for:
   - OAuth state lifecycle
   - owner isolation (RLS)
   - missing-access database guidance
   - multi-database selection path

## Open Questions

- Should one user be allowed multiple Notion workspace connections, or exactly one for v1?
- Should source discovery be on-demand only, or also background refreshed?
- Do we want immediate schema sync on selection, or lazy sync on first pipeline run?
- Should `data_targets` be auto-created for all discovered sources, or only explicit user selections?

## Recommendation

For v1, implement:

- one Notion connection per user
- explicit user-selected databases only
- immediate schema sync on selection
- `connector_instances` as the top-level connection object, with separate credential/state/source tables for security and lifecycle clarity

This gives a concrete onboarding flow, preserves current domain model direction, and avoids leaking auth complexity into existing product surfaces.
