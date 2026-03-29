# Tech Debt: Icon search miss logging rejects runtime IDs

## ID

- `td-2026-03-29-icon-search-miss-runtime-id-uuid-mismatch`

## Status

- **Fixed in repo** — Migration `20260329120000_icon_search_misses_runtime_ids_text.sql` alters `icon_search_misses.job_id` and `job_run_id` from `uuid` to `text` so prefixed runtime IDs (e.g. `loc_...`) insert correctly.

## Where

- **Backend:** `app/services/job_execution/handlers/search_icon_library.py`
- **Backend:** `app/services/icon_catalog_service.py`
- **Backend:** `app/repositories/icon_catalog_repository.py`
- **DB migration:** `supabase/migrations/20260328120000_icon_library.sql` (initial table); `supabase/migrations/20260329120000_icon_search_misses_runtime_ids_text.sql` (column types)
- **Bootstrap pipeline:** `product_model/bootstrap/jobs/notion_place_inserter.yaml` (`pipeline_icon_image`)

## Observed behavior

- `pipeline_icon_image` resolves the search query from `google_places_selected_place.displayName` and searches the first-party icon catalog.
- When no icon tag match exists, the step tries to record a miss in `icon_search_misses`.
- The step degraded with `image_url: ""` and an error like `record_miss failed: invalid input syntax for type uuid: "loc_..."`.

## Steps to reproduce (before fix)

1. Run the starter job with `pipeline_icon_image` enabled.
2. Use a place whose `displayName` does not match any icon tag, for example `Nicollet Island Inn`.
3. Let `step_template_search_icon_library` execute with default config (`record_miss: true`).
4. Observe the step output stayed empty and the processing log showed `record_miss failed`.

## Expected behavior

- A no-match icon search should soft-complete with empty outputs and optionally log a miss row for later catalog curation.
- Miss logging should not error just because the runtime uses prefixed IDs such as `loc_...`.

## Why this existed / notes

- **Proven:** `icon_search_misses.job_id` and `icon_search_misses.job_run_id` were initially declared as `uuid` columns in `20260328120000_icon_library.sql`.
- **Proven:** `SearchIconLibraryHandler` passes `ctx.job_id` and `ctx.run_id` into `record_miss(...)`.
- **Proven:** In this runtime, `job_id` can be a prefixed application ID like `loc_3adde6001eeb41ebaebc43eca376de80`, which is not a PostgreSQL UUID literal.
- Result: the miss insert failed even though the search itself merely had no matches.

## Resolution

- Columns widened to `text` via `ALTER TABLE ... USING job_id::text` / `job_run_id::text` so existing UUID values remain valid string forms and new rows accept any runtime id string.

## Goal

- Icon search misses are recorded without degrading the step when the pipeline runtime uses non-UUID app identifiers.

## Out of scope for this note

- Improving icon relevance or adding more icons/tags for `Nicollet Island Inn`.
