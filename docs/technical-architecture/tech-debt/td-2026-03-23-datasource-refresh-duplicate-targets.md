# Tech Debt: Data source refresh duplicates targets / pollutes store

## ID

- `td-2026-03-23-datasource-refresh-duplicate-targets`

## Status

- Open

## Where

- **UI:** `notion_pipeliner_ui/src/routes/DataTargetsPage.tsx` — **Refresh** calls `refreshNotionSources` → `POST .../refresh-sources`.
- **API:** `app/routes/notion_oauth.py` — `refresh_connection_sources` (`POST /management/connections/{id}/refresh-sources`), `list_connection_data_sources`, `select_data_sources` (creates `data_targets`).
- **Discovery / persistence:** `app/services/notion_oauth_service.py` — `refresh_sources()` searches Notion, resolves IDs, `upsert_batch` into `connector_external_sources`.
- **External sources repo:** `app/repositories/postgres_repositories.py` — `PostgresConnectorExternalSourcesRepository.upsert_batch` (conflict key `owner_user_id, connector_instance_id, external_source_id`).
- **Related prior work:** GET `/management/data-targets` deduplicates by `(connector_instance_id, external_target_id)` (work log: data-targets-dedup); list-level dedup does not stop duplicate rows if identities diverge.

## Observed behavior

- Using **Refresh** on the Data Targets page (re-discovering Notion data sources) is observed to **pull back** databases and contribute to **duplicate data targets** (or duplicate-looking tracked databases) instead of purely refreshing metadata in place.
- Product expectation: **refresh should be idempotent** with respect to stored targets—re-sync discovery and metadata **without** polluting `connector_external_sources` or `data_targets` with redundant rows for the same logical Notion database.

## Steps to reproduce

1. Connect Notion and open **Data targets** (`/data-targets`).
2. Note existing discovered sources and tracked targets.
3. Click **Refresh** (re-run discovery).
4. Compare lists / DB: duplicates or redundant targets appear (exact UI/DB state to confirm during fix).

## Expected behavior

- Refresh updates **last seen** / display metadata and keeps a **single stable identity** per logical database (data source) per user connection.
- No new `data_targets` rows unless the user explicitly selects new sources; no duplicate external-source rows for the same underlying database.

## Why this exists / notes

- **Upsert key** on `connector_external_sources` is `external_source_id`. If Notion search returns items whose resolved **data source ID** differs across refreshes (or both `database` and `data_source` shapes appear with different IDs), the same logical DB could get **multiple rows**.
- **`select_data_sources`** builds `target_id` as `target_notion_{eid...}` from `external_source_id`; if that ID changes between discovery and selection, a **second target** can be created for what the user considers the same DB (while GET list dedup may hide one symptom but pipelines may still reference stale IDs).
- **Proven vs inferred:** User report + code paths above; root cause needs confirmation with DB inspection (duplicate `external_source_id` vs duplicate `display_name`/parent) and optional Notion API response comparison before/after refresh.

## Goal

- **Idempotent refresh:** one canonical row per logical Notion database per connection in `connector_external_sources`, aligned with `data_targets.external_target_id`, with a defined merge strategy when Notion IDs change.
- **No silent target proliferation** on refresh alone; selection remains the only path that materializes new `data_targets` unless product explicitly decides otherwise.

## Suggested follow-ups

1. Reproduce: capture `connector_external_sources` rows for one user before/after refresh (count, `external_source_id`, `display_name`, `external_parent_id`).
2. Define **canonical key** (e.g. stable Notion database id vs data source id) and migration for merging duplicates.
3. Add tests: refresh twice does not increase row count for unchanged workspace; selection idempotency when target already exists (already partially handled in `select_data_sources`).
4. Align UI copy if “Refresh” is only discovery—not “re-add targets.”

## Out of scope for this note

- Notion API version bumps unrelated to identity stability.
- Broader dedup of unrelated bootstrap vs per-source targets (already partially addressed in management list).
