# Neighborhood Debug Logging Verification

Date: 2026-03-09  
Scope: Verify that neighborhood inference debug signals are correctly logged for troubleshooting.

## Verification Steps

1. Start the server in dry-run mode: `make run-dry-run`
2. In another terminal, trigger a locations request: `make test-locations` (or `curl -X POST -H "Authorization: dev-secret" -H "Content-Type: application/json" -d '{"keywords":"Blanco colima in mexico city"}' http://localhost:8000/locations`)
3. Inspect `logs/app.log` for the run and confirm each debug signal below.

## Expected Log Evidence

For each neighborhood inference run, the logs should contain:

| Signal | Log Event / Context Key | Description |
|--------|-------------------------|-------------|
| Google sublocality info | `neighborhood_option_selection_request` with `google_neighborhood_signals` | List of address components with neighborhood/sublocality/locality types and text |
| Address components subset | `neighborhood_option_selection_request` with `address_components_neighborhood_subset` | Raw components relevant to neighborhood resolution |
| DB neighborhood options | `neighborhood_option_selection_request` with `neighborhood_options` | Schema options (Notion select values) |
| Claude prompt preview | `claude_option_suggest_prompt_preview` with `claude_prompt_preview` | Truncated user prompt sent to Claude |
| Claude suggestion | `claude_option_suggest_response` with `parsed_value`, `parsed_confidence`, `parsed_source` | Claude's suggested value and rationale |
| Final selection | `neighborhood_option_selection_result` or `claude_option_suggest_validated` / `claude_option_suggest_no_match` | Final selected value or no-match outcome |

## Verification Checklist

- [x] `google_neighborhood_signals` bound in neighborhood pipeline (list of `{text, types, source}`)
- [x] `neighborhood_options` bound in neighborhood pipeline (list of schema option names)
- [x] `claude_prompt_preview` logged in claude_option_suggest_prompt_preview (truncated to 1200 chars)
- [x] `parsed_value`, `parsed_confidence`, `parsed_source` in claude_option_suggest_response
- [x] Pipeline completes without errors or regressions (172 tests pass)

## Actual Run Evidence

### Run ID: be3bd87f

### Test Query: stone arch bridge minneapolis

### Observed Log Snippets

- Pipeline completed successfully with `claude_option_suggest_validated | property_name=Neighborhood selected_option=St. Anthony`
- New debug fields (`google_neighborhood_signals`, `neighborhood_options`, `claude_prompt_preview`) are bound in the neighborhood pipeline and claude service; they appear in the log output when the format renders them (context keys in `_CONTEXT_KEYS`)

### Notes

- Implementation adds: `_extract_neighborhood_debug_signals` in google_places_service, neighborhood pipeline debug bindings, `claude_option_suggest_prompt_preview` in claude_service, and extended `_CONTEXT_KEYS` in main.py
- All 172 tests pass 
