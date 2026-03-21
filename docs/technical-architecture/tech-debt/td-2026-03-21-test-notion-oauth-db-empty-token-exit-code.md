# Tech Debt: `test_notion_oauth_db.py` empty `--token` exit code

## ID

- `td-2026-03-21-test-notion-oauth-db-empty-token-exit-code`

## Status

- Open

## Symptom

`tests/test_test_notion_oauth_db.py::test_script_exits_1_when_token_empty` fails: the test expects `scripts/test_notion_oauth_db.py` to exit with code **1** when invoked with `--token` and an **empty** string, but the script currently exits with **0**.

Observed during full `pytest` runs (2026-03-21); other suites (including newer feature tests) pass independently.

## Why this matters

- Full test suite should be green in CI and locally so regressions are not masked.
- The test encodes an explicit contract: invalid/empty token should be a hard failure for this diagnostic script.

## Suggested fix

1. Inspect `scripts/test_notion_oauth_db.py` argument handling for `--token` (and any env fallback such as `NOTION_OAUTH_TEST_TOKEN`).
2. Treat empty string the same as missing token when that is unsafe, or document why empty is valid and **update the test** if behavior is intentional.
3. Re-run: `pytest tests/test_test_notion_oauth_db.py -q` and full `pytest`.

## Acceptance criteria

- `test_script_exits_1_when_token_empty` passes **or** the test is revised with a documented, reviewed behavior.
- Full `pytest` completes without this failure.

## References

- Test: `tests/test_test_notion_oauth_db.py`
- Script: `scripts/test_notion_oauth_db.py`
