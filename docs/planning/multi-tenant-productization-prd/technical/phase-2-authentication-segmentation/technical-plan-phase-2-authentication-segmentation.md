# Technical Plan: Phase 2 Authentication and Segmentation

## Status

- In progress (p2_pr01 schema implemented)

## Schema (p2_pr01)

- **Enum:** `user_type_enum` — `ADMIN`, `STANDARD`, `BETA_TESTER`
- **Table:** `user_profiles` — `user_id` (PK, FK auth.users), `user_type`, `invitation_code_id` (FK invitation_codes), `created_at`, `updated_at`
- **Table:** `invitation_codes` — `id`, `code` (unique, 20 chars), `date_issued`, `date_claimed`, `issued_to`, `platform_issued_on`, `claimed`, `claimed_at`, `user_type`, `claimed_by_user_id` (FK auth.users), `created_at`; constraints: code uniqueness, length, claim-integrity (claimed ↔ timestamps)

## Objective

Deliver a minimal but complete authentication entry flow and post-login dashboard while introducing user-type segmentation and invite-code-based onboarding controls.

## Scope

### UI flow

- Public landing page with a top-right `Sign In / Sign Up` link.
- Basic auth page that supports sign-in and sign-up.
- On successful auth, redirect to dashboard landing page.
- Dashboard remains intentionally minimal for this phase and only exposes:
  - `Run Location Inserter (with dummy data)`

### User types

Support exactly three user types in Phase 2:

- `ADMIN`
- `STANDARD`
- `BETA_TESTER`

These types must be persisted in user profile data and available to authorization and feature-gating checks.

### Invitation codes

Introduce a backend invitation code table linked to user profile information.

Required invitation-code fields:

- `code` — random string, 20 characters, unique
- `date_issued` — datetime
- `date_claimed` — datetime, nullable
- `issued_to` — free text (email or username)
- `platform_issued_on` — free text
- `claimed` — boolean
- `claimed_at` — datetime, nullable
- `user_type` — enum (`ADMIN`, `STANDARD`, `BETA_TESTER`)

Claim behavior:

- Codes are single-use.
- Claim marks `claimed = true` and sets claim timestamps.
- Sign-up using a valid code assigns the user profile `user_type` from the code.

### Operator workflow

Add a manually run script/CLI to generate invitation codes for operator workflows (including beta tester onboarding).

## Deliverables

1. Public landing page and auth page route(s).
2. Protected dashboard landing route after authentication.
3. User-profile `user_type` support with enum validation.
4. Invitation-code persistence model and claim lifecycle.
5. Manual invitation-code generation script/CLI and usage docs.

## Acceptance criteria

- Unauthenticated users land on the public landing page and can reach auth from the top-right action.
- Successful sign-in/sign-up routes users to dashboard landing.
- Protected routes reject unauthenticated access.
- Invitation code creation path produces unique 20-character codes.
- Code-claim path is single-use and timestamps claims.
- Users created via invitation code receive the invitation code `user_type`.
- Dashboard remains minimal and only includes `Run Location Inserter (with dummy data)` in this phase.

## Out of scope

- Full pipeline-management UI
- Advanced RBAC beyond the initial three user types
- Team/workspace membership model changes
