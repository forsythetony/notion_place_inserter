# p4_pr03 - Validation, Observability, Tests, and Docs

## Objective

Harden Phase 4 with database-native guardrails, expand run/usage observability verification for datastore-backed mode, add or refresh tests, and complete operator documentation for Phase 4 manual validation.

## Scope

- Add DB-native guardrails where applicable: check constraints, triggers, or application-level validation that runs before writes
- Expand run/usage observability: ensure logs and any existing metrics work correctly with Postgres-backed runs
- Add or refresh tests for: Postgres repository implementations, definition resolution from Postgres, run persistence, RLS behavior
- Update operator docs: required env vars, manual validation walkthrough, Phase 4 workflow (bootstrap, run, inspect runs in DB)
- Reconcile or deprecate YAML-specific tooling (e.g., `make show-runs` may need a DB equivalent or doc update)

## Expected changes

- New or updated tests for Postgres repositories and run persistence
- Check constraints or validation logic in migrations or application layer
- Documented manual validation steps
- Phase 4 index and ticket docs updated with verification checklists
- Operator runbook for Phase 4 (bootstrap, run, inspect, troubleshoot)

## Acceptance criteria

- Critical paths (resolution, validation, execution, run persistence) are test-covered or have explicit manual checklist
- DB-native guardrails are in place where appropriate
- Logs are sufficient to diagnose execution and persistence failures in datastore mode
- Operators can follow docs to bootstrap, run, and verify Phase 4 behavior
- Phase 4 completion definition is satisfied

## Out of scope

- Phase 5 visual editing
- Full UI for run history
- Secret reference backend migration

## Dependencies

- Requires p4_pr01 and p4_pr02.

---

## Manual validation steps (after implementation)

1. Run full test suite: `pytest tests/ -v` (including Postgres repo tests).
2. Bootstrap: start backend, sign in, confirm definitions load from Postgres.
3. Run: trigger a job and verify execution; inspect runs in Postgres.
4. Durable edits: edit a definition, run, restart; confirm edits persist.
5. RLS: verify tenant isolation via different user or direct DB access.
6. Follow operator runbook for Phase 4 manual validation.

## Verification checklist

- [x] Tests cover critical Phase 4 paths.
- [x] DB guardrails are in place.
- [x] Logs support debugging.
- [x] Operator docs are complete.
- [x] Phase 4 completion definition satisfied.
