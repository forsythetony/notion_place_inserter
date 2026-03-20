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

1. **Run a job and confirm run hierarchy persisted:**
   - Trigger async: `POST /triggers/{user_id}/locations` with `{"keywords": "park"}`.
   - Check `product_model/tenants/<owner_user_id>/runs/` for `{run_id}.yaml` (JobRun).
   - Check nested `runs/{run_id}/stages/`, `pipelines/`, `steps/` for StageRun, PipelineRun, StepRun YAML files.
2. **Confirm usage records:** Check `runs/{run_id}/usage/` for `llm_tokens` (anthropic) and `external_api_call` (google_places, notion) YAML files.
3. **Run test suite:** `pytest tests/ -v` (including `test_yaml_run_repository`, `test_job_execution`, `test_worker_consumer`, `test_locations_route`).
4. **Ephemeral persistence:** Restart container; confirm run/usage YAML under `tenants/` is container-local and may be lost on restart.

## Verification checklist

- [x] Runs are persisted with snapshot ref and metadata.
- [x] Usage records are created.
- [x] Logging is sufficient for debugging.
- [x] Tests or manual checklist cover critical paths.
- [x] Phase 3 docs are complete and consistent.
