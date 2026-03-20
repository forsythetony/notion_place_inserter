# Run 7bb37066: Neighborhood and Sublocality Investigation

## Why this document exists

This documents what happened in run `7bb37066` from start to finish, why neighborhood/sublocality debug details were not visible in logs, and what to do so Google neighborhood data is always inspectable.

## Executive conclusion

- The run completed successfully and resolved most properties.
- `Neighborhood` was intentionally left unset because Claude returned `no_match`.
- The expected neighborhood debug lines (`neighborhood_option_selection_request`, `neighborhood_google_signals_received`, `neighborhood_no_google_sublocality_signals`) were not emitted in this run's log output.
- Current uncommitted code changes in the repo add exactly these missing diagnostics and context keys, which strongly indicates the observed run did not include that newer instrumentation path (or it ran before those changes were active).

## End-to-end timeline for run `7bb37066`

### 1) Request received

- `pipeline_request_started` with `keywords_preview=Blanco colima in mexico city`
- `dry_run=True`

### 2) Research stage

- `load_latest_schema` succeeded.
- `query_to_google_cache` succeeded:
  - `rewrite_query_with_claude` succeeded.
  - `google_places_to_cache` succeeded.

### 3) Property resolution stage

- Property fan-out started and multiple pipelines ran in parallel.
- `neighborhood_Neighborhood` pipeline started.
- `infer_neighborhood` ran and completed successfully (~3400ms).
- Claude emitted:
  - `claude_option_suggest_no_match | property_name=Neighborhood`
- Then:
  - `format_neighborhood` succeeded.
  - `neighborhood_Neighborhood` pipeline completed.

Interpretation: the system did execute neighborhood inference, but no valid existing option or suggestion was selected, so the field remained empty.

### 4) Remaining stages

- `image_resolution` completed.
- `global_pipeline_completed` and `pipeline_request_completed` both succeeded.

## What is missing (and why it matters)

Expected diagnostic events for neighborhood debugging were not present:

- `neighborhood_option_selection_request` (should include `candidate_context`, options, etc.)
- `neighborhood_google_signals_received` or `neighborhood_no_google_sublocality_signals`

Without these, we cannot answer from this log alone:

- What `addressComponents` sublocality/neighborhood components Google returned.
- Whether `google_neighborhood_signals` existed at all.
- What exact neighborhood evidence Claude saw.

## Evidence from current codebase state

The working tree currently contains uncommitted instrumentation changes that directly address this gap:

- `app/services/google_places_service.py`
  - Adds `_extract_neighborhood_debug_signals(...)`
  - Adds `google_neighborhood_signals` to normalized place payload.
- `app/pipeline_lib/stage_pipelines/google_places.py`
  - Merges `google_neighborhood_signals` from details into the cached place object.
- `app/custom_pipelines/neighborhood.py`
  - Logs `neighborhood_google_signals_received` or `neighborhood_no_google_sublocality_signals`
  - Binds `google_neighborhood_signals`, `neighborhood_options`, and `address_components_neighborhood_subset`
  - Emits `neighborhood_option_selection_request` with those fields.
- `app/main.py`
  - Extends `_CONTEXT_KEYS` so those fields render in log lines.

This aligns with your concern: run `7bb37066` log output does not show these lines, but the repo now has code intended to produce them.

## Most likely root cause

Most likely scenario:

1. The observed run executed before these instrumentation edits were active in the running process, or against an older running server/container image.
2. Therefore, the run produced only baseline orchestration logs plus Claude's `no_match`, not the newer neighborhood diagnostics.

Less likely but possible:

- A logger format/filter mismatch suppressed bound context keys (but this would not suppress message names themselves).
- Different runtime path/module instance than expected.

## What this run tells us about neighborhood behavior

- Neighborhood inference depends on model selection with suggestion support.
- For this Mexico City location, model returned `no_match`; that is safe behavior (prefer empty over wrong).
- But observability is insufficient in this run to verify what Google neighborhood/sublocality evidence existed.

## Recommendations

## Priority 1: Ensure Google neighborhood package is always visible

1. Keep and ship the current instrumentation changes.
2. Add one explicit pre-LLM log event in neighborhood inference with:
   - `place_id`
   - `formattedAddress`
   - `addressComponents` count
   - `google_neighborhood_signals`
   - `address_components_neighborhood_subset`
3. Add one explicit post-normalization log event in `GooglePlacesService`:
   - `place_id`
   - raw neighborhood extraction result
   - extracted debug signals

Result: you can confirm whether Google returned neighborhood/sublocality data before Claude is invoked.

## Priority 2: Make run-level debugging deterministic

1. Include `run_id` in all Google service diagnostic logs.
2. On each pipeline request, log a single "google_place_payload_snapshot" (trimmed fields) before property fan-out.
3. Keep payload snapshot size bounded (truncate strings, cap array lengths) to avoid log bloat.

Result: every run has one canonical payload record you can inspect end-to-end.

## Priority 3: Add confidence and guardrails

1. Keep `None` on weak evidence (`no_match`) rather than forcing a neighborhood.
2. Add structured output from Claude for neighborhood:
   - selected value
   - confidence
   - source evidence token(s)
3. Require minimum confidence or direct Google signal before accepting a suggestion.

Result: fewer false positives and better explainability.

## Validation plan (quick)

1. Run one dry-run query for a known place in a known neighborhood.
2. Confirm log includes:
   - `neighborhood_google_signals_received` (or explicit no-signals event)
   - `neighborhood_option_selection_request` with neighborhood evidence fields
   - Claude request/response/validated (or no-match)
3. Verify the final neighborhood outcome matches expectation:
   - exact option match, new suggestion (if intended), or `None` with clear evidence.

## Operational checklist for this specific concern

- [ ] Ensure runtime process is restarted after instrumentation changes.
- [ ] Confirm logs are being read from the active runtime sink (`logs/app.log` for that process).
- [ ] Re-run `Blanco colima in mexico city` with a fresh run id.
- [ ] Verify Google neighborhood package appears in logs for that new run.
- [ ] If not present, add/verify the pre-LLM payload snapshot log in the Google service path.

## Bottom line

Run `7bb37066` shows a safe neighborhood outcome (`no_match`), but not enough evidence visibility. The current code changes already move in the right direction; the next step is to run with those changes active and verify that the Google neighborhood/sublocality payload is emitted per run so debugging is definitive.
