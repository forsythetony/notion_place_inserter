# Notion Database ID vs Data Source ID — Fix Plan

**Date:** 2026-03-16  
**Source:** `temp/deploy-worker-error-logs_2026-03-15_23-11-38.log` + OAuth probe findings  
**Status:** Planning

---

## Executive Summary

Production runs fail because the codebase treats **database IDs** and **data source IDs** interchangeably. Notion’s API distinguishes them:

- **Database ID** (e.g. `1e2a5cd4-f107-490f-9b7a-4af865fd1beb`): Returned by search when `object=database`; used with `databases.retrieve()`.
- **Data source ID** (e.g. `9592d56b-899e-440e-9073-b2f0768669ad`): Child of a database; used with `data_sources.retrieve()` and `pages.create(parent={"data_source_id": "..."})`.

The Notion API for `pages.create` expects `parent.data_source_id` to be a **data source ID**, not a database ID. Passing a database ID causes:

```
Could not find data_source with ID: 1e2a5cd4-f107-490f-9b7a-4af865fd1beb
```

A second issue is `ai_select_relation_target_not_found` for `target_locations`: the related target is missing from the snapshot for some owners.

---

## Observed Errors (from deploy-worker-error-logs)

| Error | Frequency | Context |
|-------|-----------|---------|
| `Could not find data_source with ID: 1e2a5cd4-f107-490f-9b7a-4af865fd1beb` | 4 attempts (terminal) | `notion_create_page_data_source_failed` during page creation |
| `ai_select_relation_target_not_found \| related_db=target_locations` | Every pipeline | Location relation step cannot find target data |

**ID mapping (verified via OAuth probe):**

| Display Name   | Database ID                              | Data Source ID (correct for API)        |
|----------------|------------------------------------------|----------------------------------------|
| Places to Visit| `1e2a5cd4-f107-490f-9b7a-4af865fd1beb`   | `9592d56b-899e-440e-9073-b2f0768669ad` |
| Locations      | `544d5797-9344-4258-aed6-1f72e66b6927`   | `cfecaf05-306e-48ac-9d8b-bb14e8243d44` |

---

## Root Causes

### 1. OAuth selection stores database ID, but page creation needs data source ID

**Flow:**

1. `NotionOAuthService.refresh_sources()` calls `/v1/search` with `object=data_source`.
2. Search returns items with `object=database`; `item["id"]` is the **database ID**.
3. `connector_external_sources` stores `external_source_id = db_id` (database ID).
4. `select_data_sources` saves `external_target_id = eid` (database ID) into `data_targets`.
5. Job execution uses `target_data.external_target_id` for `pages.create(parent={"data_source_id": id})`.
6. Notion API expects a data source ID and fails with 404.

**Relevant code:**

- `app/services/notion_oauth_service.py` — `refresh_sources()` stores `item["id"]` (database ID).
- `app/routes/notion_oauth.py` — `select_data_sources` saves `external_target_id=eid`.
- `app/services/job_execution/job_execution_service.py` — `data_source_id = target_data.get("external_target_id")`.
- `app/services/notion_service.py` — `create_page_with_token(..., data_source_id)` → `parent: {"data_source_id": data_source_id}`.

### 2. `target_locations` missing from snapshot for some owners

**Flow:**

1. Job `notion_place_inserter` has `ai_select_relation` with `related_db: target_locations`.
2. `JobDefinitionService.resolve_for_run()` collects `related_target_ids` and fetches each via `target_service.get_by_id(tid, owner)`.
3. For Postgres owners, `target_locations` is **not** created by bootstrap; only `target_places_to_visit` is.
4. `target_service.get_by_id("target_locations", owner)` returns `None`.
5. `snapshot["targets"]["target_locations"]` is absent → `ai_select_relation_target_not_found`.

**Relevant code:**

- `app/services/postgres_seed_service.py` — bootstrap creates only `target_places_to_visit`.
- `app/services/job_definition_service.py` — `_collect_related_target_ids()` includes `target_locations`.
- `app/services/job_execution/handlers/ai_select_relation.py` — `targets.get(related_db)` is `None`.

---

## Fix Plan

### Fix 1: Resolve database ID → data source ID at OAuth selection time (preferred)

**Goal:** Store the correct data source ID in `external_target_id` when the user selects a database.

**Changes:**

1. **`app/services/notion_oauth_service.py` — `refresh_sources()`**
   - For each search result with `object=database`:
     - Call `databases.retrieve(database_id=db_id)`.
     - Read `data_sources[0].id` as the data source ID.
     - Store that data source ID as `external_source_id` instead of the database ID.
   - For results with `object=data_source`, keep storing `item["id"]` as-is.
   - Add error handling and fallback if `data_sources` is empty.

2. **`connector_external_sources` schema**
   - No schema change needed; `external_source_id` continues to hold the ID we choose to store.
   - Optionally add `external_database_id` if both IDs are needed for future use.

3. **Backfill / migration**
   - Existing rows with database IDs need resolution. Options:
     - One-time migration: for each `external_source_id` that fails `data_sources.retrieve`, try `databases.retrieve`, get `data_sources[0].id`, update.
     - Or: resolve at runtime (Fix 2) until migration is run.

**Alternative:** Resolve at runtime in `NotionService.create_page_with_token` (see Fix 2).

---

### Fix 2: Resolve database ID → data source ID at page-creation time (runtime fallback)

**Goal:** If `external_target_id` is a database ID, resolve it to a data source ID before calling `pages.create`.

**Changes:**

1. **`app/services/notion_service.py`**
   - Add `_resolve_to_data_source_id(access_token, configured_id) -> str`:
     - Try `data_sources.retrieve(configured_id)`; if success, return `configured_id`.
     - Else try `databases.retrieve(configured_id)`; if success and `data_sources`, return `data_sources[0].id`.
     - Else re-raise.
   - In `create_page_with_token`, call `data_source_id = _resolve_to_data_source_id(access_token, data_source_id)` before building the payload.

2. **Caching**
   - Consider caching `(configured_id → data_source_id)` per token/session to avoid repeated API calls.

**Pros:** Works for existing data without migration.  
**Cons:** Extra API call per page create; does not fix schema sync or `ai_select_relation` which also use `external_target_id`.

---

### Fix 3: Support `parent.database_id` when API allows it

**Goal:** Use `parent: {"database_id": id}` when the ID is a database ID, if the Notion API version supports it.

**Context:** Notion API version `2022-06-28` may support `database_id` for page parent. Newer versions (e.g. 2025-09-03) use `data_source_id`.

**Changes:**

1. Check Notion API docs for `pages.create` and the project’s API version.
2. If `database_id` is supported:
   - In `create_page_with_token`, try `data_sources.retrieve(id)`.
   - On success → use `parent: {"data_source_id": id}`.
   - On 404 → use `parent: {"database_id": id}` (treat as database ID).

**Note:** The current error indicates the API is interpreting the ID as a data source. Verifying support for `database_id` is required before relying on this.

---

### Fix 4: Ensure `target_locations` exists for all owners

**Goal:** `target_locations` is present in the snapshot so `ai_select_relation` can resolve the Locations database.

**Changes:**

1. **`app/services/postgres_seed_service.py` — bootstrap**
   - Create `target_locations` with `external_target_id=PLACEHOLDER_EXTERNAL_TARGET_ID` (or equivalent) when provisioning an owner, similar to `target_places_to_visit`.

2. **`app/routes/notion_oauth.py` — `select_data_sources`**
   - When the user selects databases, detect a “Locations” database (e.g. by `display_name` or a convention).
   - Create or update `target_locations` with the correct `external_target_id` (data source ID after Fix 1).
   - Ensure both `target_places_to_visit` and `target_locations` are updated when the user selects both.

3. **Display name mapping**
   - Define a stable way to map selected sources to `target_places_to_visit` vs `target_locations` (e.g. display name, config, or selection order).

---

### Fix 5: Use correct ID type in schema sync and `ai_select_relation`

**Goal:** All Notion API calls use the correct ID type.

**Affected paths:**

| Component | Uses | Fix |
|-----------|------|-----|
| `SchemaSyncService` | `target.external_target_id` for `get_raw_schema_for_data_source` | After Fix 1, `external_target_id` is data source ID; no change if already correct. |
| `SchemaCache._iter_data_source_schemas` | `configured_id` for both `databases.retrieve` and `data_sources.retrieve` | Already handles both; ensure `external_target_id` is data source ID. |
| `AiSelectRelationHandler` | `target_data.external_target_id` or `get_data_source_id(display_name)` for `data_sources.query` | `data_sources.query` expects data source ID; ensure `external_target_id` is data source ID. |
| `NotionService.create_page_with_token` | `data_source_id` for `parent` | Primary fix target (Fix 1 or 2). |

---

## Implementation Order

1. **Fix 1** — Resolve and store data source ID at OAuth selection (source of truth).
2. **Fix 4** — Bootstrap and update `target_locations` so `ai_select_relation` has a target.
3. **Fix 2** (optional) — Runtime resolution as fallback for existing database IDs until migration.
4. **Fix 5** — Audit and fix any remaining ID usages.
5. **Fix 3** (optional) — Explore `database_id` support if needed.

---

## Verification

1. **OAuth probe:** `make test-notion-oauth-db DATABASE_ID_ARG="--data-source-id <id>"` succeeds for both data source and database IDs.
2. **Page creation:** Run a full pipeline; page creation succeeds with OAuth token.
3. **Relation step:** `ai_select_relation_target_not_found` no longer appears; Location relation is populated.
4. **Schema sync:** Schema sync works for newly connected databases.

---

## References

- `scripts/test_notion_oauth_db.py` — OAuth probe with database/data_source fallback.
- `docs/technical-architecture/incident_investigations/notion-data-source-error-findings-2026-03-15.md` — Prior findings.
- Notion API: [Parent object](https://developers.notion.com/reference/parent-object), [Create page](https://developers.notion.com/reference/post-page).
