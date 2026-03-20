# Notion Data Source Error Findings (Log-Only)

## Scope and Source

This document uses only one source:

- `temp/deployed-worker-error-logs_2026-03-15_20-55-58.log`

No other logs, code, config, docs, or environment files were used for this analysis.

## Observed Failure Pattern

Across multiple runs and retries, the terminal error is consistent:

- `Could not find data_source with ID: 1e2a5cd4-f107-490f-9b7a-4af865fd1beb.`
- Error class in log: `APIResponseError`
- Message guidance in error: "Make sure the relevant pages and databases are shared with your integration 'Place Inserter'."

The same Notion error repeats across:

- multiple `job_id` values
- multiple `run_id` values
- retries up to attempt `4`

This indicates a persistent configuration/access problem for a specific Notion data source ID, not a one-off transient failure.

## Timeline Signals from the Same Log

1. Worker starts processing a run and reaches stage execution.
2. Cover upload steps complete successfully (`notion_file_upload_*` with `status=uploaded`).
3. Pipeline fails afterward with `Could not find data_source with ID ...`.
4. Worker retries (`delay_seconds=5`, `30`, `60`) and fails again with the exact same Notion error.
5. After max retries, run is marked failed and a new queued run repeats the same pattern.

## What This Strongly Suggests

Based on this log alone, the most likely root cause is:

- The integration token being used at write time does not have access to the Notion data source ID `1e2a5cd4-f107-490f-9b7a-4af865fd1beb`, or
- The data source reference being used by the pipeline is stale/invalid for the current Notion workspace/integration context.

Confidence from this log: **high** for a Notion data source access/reference issue.

## What Cannot Be Proven from This Log Alone

- Which exact token was used on each failed write.
- Whether the data source still exists in Notion at the time of each attempt.
- Whether the integration was unshared, reinstalled, or switched between retries.
- Whether the stored target mapping points at the wrong workspace/data source.

## Immediate Recommendations (Notion-Focused)

1. Verify data source access in Notion UI
   - Confirm the target database/data source exists.
   - Confirm it is shared with the "Place Inserter" integration.
2. Reconfirm integration context
   - Ensure the same workspace that owns the data source is the one authorized for this run path.
3. Re-select/re-save target data source mapping
   - Force refresh of selected data source binding to avoid stale IDs.
4. Run one manual test after re-sharing/re-binding
   - Expect first-run success without repeating `attempt=1..4` failures.

## Logging and Observability Improvements (For This Notion Issue)

If root cause is not immediately confirmed, add/strengthen logs around the failing Notion write path:

1. Add structured context on Notion write failure
   - `notion_data_source_id`
   - `owner_user_id`
   - `job_id`, `run_id`, `attempt`
   - token source type (`oauth` vs `global`) without logging secrets
2. Add preflight access check logging
   - Log success/failure of a lightweight "can access this data source" call before create-page.
3. Add failure classification
   - `error_domain=notion`
   - `error_kind=data_source_not_found`
   - preserve raw Notion error code/message when available
4. Add deduplicated incident signal
   - Counter/alert when same `notion_data_source_id` fails N times within M minutes.

## Suggested Next Steps (If Still Failing)

1. Reproduce with a single known test keyword and capture one run end-to-end.
2. Confirm whether failure occurs before or only at final Notion page create (this log suggests final write phase).
3. If still failing, compare successful vs failing run contexts by:
   - data source ID
   - integration identity/workspace context
   - token source type
4. Keep retries as-is for now, but consider fast-failing this specific deterministic Notion error after 1 attempt to reduce noisy retry loops.

## Bottom Line

Using only `temp/deployed-worker-error-logs_2026-03-15_20-55-58.log`, the failure pattern points to a **persistent Notion data source access/reference problem** for ID `1e2a5cd4-f107-490f-9b7a-4af865fd1beb`, not an intermittent transient error.
