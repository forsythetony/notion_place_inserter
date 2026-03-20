# p1_pr07 - Tests, Observability, and API Doc Updates

## Objective

Harden the migration with targeted tests, durable lifecycle visibility, and updated API documentation.

## Scope

- Add/adjust tests for:
  - enqueue path with Supabase queue adapter
  - worker success/failure lifecycle persistence
  - idempotency/duplicate handling behavior
- Update `openapi.yaml` descriptions for durable queue-backed async behavior.
- Improve structured logs for correlation by `job_id` and `run_id`.

## Expected changes

- New/updated tests under `tests/`.
- `openapi.yaml` wording and examples aligned to migrated runtime.
- Logging improvements in route + worker paths.

## Acceptance criteria

- Critical migration paths covered by automated tests.
- API docs match real runtime behavior.
- Logs allow tracing enqueue -> worker -> completion/failure by identifiers.

## Out of scope

- Broad test suite redesign unrelated to migration.

## Dependencies

- Requires PR 05 (and PR 06 if frontend-trigger integration tests are included).
