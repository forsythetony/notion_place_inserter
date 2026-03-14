# p3_pr08 - Runs, Usage Observability, and Docs

## Objective

Implement run and usage record persistence, add observability, and harden Phase 3 with tests and operational documentation.

## Scope

- Implement `YamlRunRepository` for `JobRun`, `StageRun`, `PipelineRun`, `StepRun`
- Implement `UsageRecord` persistence (or equivalent) for `llm_tokens`, `external_api_call` usage types
- Add `UsageAccountingService` to record usage during execution
- Persist runs with `definition_snapshot_ref`, `trigger_payload`, status, timestamps, error summary
- Add structured logging around job execution, run creation, and usage recording
- Add/expand tests for: definition resolution, validation, snapshot execution, trigger dispatch
- Update docs: required env vars, manual validation walkthrough, operator workflow for Phase 3

## Expected changes

- `YamlRunRepository` implementation
- Run and usage record persistence during execution
- `UsageAccountingService` integration
- Test coverage for critical Phase 3 paths
- Docs updates in phase folder and relevant READMEs

## Acceptance criteria

- Job runs are persisted with snapshot ref, payload, status, and timestamps
- Usage records are created for LLM tokens and external API calls
- Logs are sufficient to diagnose execution and persistence failures
- Critical paths (resolution, validation, execution, trigger dispatch) are test-covered or have explicit manual checklist
- Operators can follow docs to bootstrap, run, and verify Phase 3 behavior

## Out of scope

- Phase 4 Postgres migration
- Full UI for run history

## Dependencies

- Requires p3_pr01, p3_pr02, p3_pr03, p3_pr04, p3_pr07, p3_pr05, p3_pr06 (all prior stories in execution order).

---

## Manual validation steps (after implementation)

1. Run a job and confirm `JobRun`, `StageRun`, `PipelineRun`, `StepRun` records are persisted.
2. Confirm usage records are created for Claude and Google Places calls.
3. Run test suite for Phase 3 paths.
4. Follow docs to bootstrap, run job, restart container; confirm ephemeral edits are lost and bootstrap is restored.

## Verification checklist

- [ ] Runs are persisted with snapshot ref and metadata.
- [ ] Usage records are created.
- [ ] Logging is sufficient for debugging.
- [ ] Tests or manual checklist cover critical paths.
- [ ] Phase 3 docs are complete and consistent.
