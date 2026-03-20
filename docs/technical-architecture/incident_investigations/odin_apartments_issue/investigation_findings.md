# Odin Apartments Incident Investigation

Date: 2026-03-08  
Scope: Analyze `app.log` for incorrect `Tags` and `Neighborhood` values on the Odin Apartments insertion.

## Executive Findings

1. `Tags` was populated with sentence fragments because the tags pipeline allows Claude to suggest new tags and accepts any non-empty text fragments from the model output.
2. `Neighborhood` was set to `South Minneapolis` because neighborhood inference is LLM-driven with weak geographic guardrails and can pick an incorrect existing option when context is ambiguous.
3. Current log formatting hides important debug fields (selected values and candidate context), which made this harder to diagnose from logs alone.

## Evidence From Logs

Run likely associated with Odin Apartments: `run_id=4e0bdc4d`

- Pipeline starts with AdditionalContext containing Odin text:
  - `pipeline_request_started` includes `AdditionalContext: (Odin ap...)`.
- `Tags` inference path executed:
  - `tags_multi_select_request` then `claude_multi_select_request/response/validated`.
- `Neighborhood` inference path executed:
  - `neighborhood_option_selection_request` then `claude_option_suggest_request/response/validated`.
- Property resolution completed successfully, so bad values were treated as valid outputs rather than runtime failures.

## Root Cause Analysis

### 1) Tag pollution ("garbage data")

The tags pipeline currently does this:

- Calls `choose_multi_select_from_context(..., allow_suggest_new=True)`.
- In canonicalization, any unrecognized value is accepted when `allow_suggest_new=True` and title-cased.
- Those accepted values are written directly to Notion multi-select.

If Claude responds with explanatory prose or bullet points (instead of only comma-separated tag names), each fragment can be treated as a new tag candidate. This matches the observed behavior (long sentence-like tags).

Contributing code path:

- `app/custom_pipelines/tags.py` -> `allow_suggest_new=True`
- `app/services/claude_service.py` -> `_canonicalize_multi_select(...)` keeps non-option parts when suggest-new is enabled

### 2) Incorrect neighborhood (`South Minneapolis` vs Northeast Minneapolis)

Neighborhood assignment is also model-driven with suggestion enabled:

- `choose_option_with_suggest_from_context(..., allow_suggest_new=True)`.
- No coordinate/boundary validation step exists before writing the result.

For Odin Apartments, coordinates in the final record are near Northeast Minneapolis (`44.9900172, -93.2557362`), but the selected neighborhood was `South Minneapolis`. This indicates an inference error that was not checked against geography.

Contributing factors:

- Neighborhood extraction from Google address components is shallow:
  - It checks for `neighborhood` or `sublocality` type names directly.
  - If not found, it falls back to `locality` (often just `Minneapolis`), which loses directional specificity.
- LLM output is accepted if it matches an existing option or suggested value, without geo sanity checks.

Contributing code path:

- `app/services/google_places_service.py` -> `_extract_neighborhood_from_components(...)`
- `app/custom_pipelines/neighborhood.py` -> suggestion-enabled selection with no geospatial validation

## Recommendations

### High priority

1. Lock down tags to known options for this pipeline:
   - Set `allow_suggest_new=False` for `Tags`, or
   - Keep suggest-new but reject new values unless they pass strict heuristics (max length, no punctuation-heavy phrases, no sentence structure, 1-3 words).
2. Add hard post-validation for neighborhood:
   - Validate selected neighborhood against lat/lng using a boundary map (or trusted reverse geocoder neighborhood result).
   - If mismatch, prefer `None` or a safe fallback over writing likely-wrong data.

### Medium priority

3. Improve neighborhood extraction:
   - Handle broader address component variants (for example `sublocality_level_*`, other admin levels) before falling back to `locality`.
4. Add stricter response schema for Claude:
   - For tags, require JSON array output and discard invalid formats.
   - For neighborhood, require a structured response with confidence and source evidence.

### Observability

5. Include key debug fields in log format (`app/main.py` `_CONTEXT_KEYS`):
   - `candidate_context`
   - `claude_raw_value`
   - `canonical_values`
   - `claude_selected_value` / `claude_selected_values`
   - `is_new_neighborhood`

Without these keys, logs show step names but not the actual bad values that were selected.

## Suggested Preventive Tests

1. Tags: test that prose/bulleted Claude output does not create new tags.
2. Tags: test maximum token/word constraints for suggested new tags.
3. Neighborhood: test that coordinates in Northeast Minneapolis cannot resolve to `South Minneapolis`.
4. Neighborhood: test fallback behavior when neighborhood evidence is weak (`None` preferred over wrong neighborhood).

## Conclusion

Both symptoms come from permissive LLM acceptance rules, not from pipeline crashes. The primary fix is to tighten validation and constrain model outputs (especially for tags), then add geographic validation for neighborhood before writing to Notion.
