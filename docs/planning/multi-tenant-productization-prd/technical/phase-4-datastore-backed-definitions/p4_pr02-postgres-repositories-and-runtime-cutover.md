# p4_pr02 - Postgres Repositories and Runtime Cutover

## Objective

Implement Postgres-backed repository implementations that replace YAML adapters behind existing interfaces, and wire API/worker services to use them so definitions and runs are persisted in the datastore.

## Scope

- Implement Postgres repository classes for: `ConnectorTemplateRepository`, `ConnectorInstanceRepository`, `TargetRepository`, `TargetSchemaRepository`, `TriggerRepository`, `JobRepository`, `StepTemplateRepository`, `RunRepository`, `AppConfigRepository` (and any others required by Phase 3 services)
- Map domain objects to/from Postgres rows; use `jsonb` for config/snapshot payloads
- Wire `main.py` and `worker_main.py` to use Postgres repositories instead of YAML repositories
- Preserve snapshot-based execution semantics (`definition_snapshot_ref`); job execution consumes resolved snapshots
- Bootstrap seed: load or migrate initial catalog and bootstrap job into Postgres (SQL seed or migration script)
- Ensure `JobDefinitionService`, `TriggerService`, `TargetService`, `RunLifecycleAdapter`, and related services use Postgres-backed repos

## Expected changes

- New `app/repositories/postgres_*.py` (or equivalent) implementations
- Dependency injection or app wiring changes in `main.py`, `worker_main.py` to swap YAML repos for Postgres repos
- Bootstrap/seed logic to populate Postgres with catalog templates and `Notion Place Inserter` job
- No changes to domain classes, service interfaces, or execution semantics

## Acceptance criteria

- All Phase 3 repository interfaces have Postgres implementations
- API and worker use Postgres repositories instead of YAML
- Trigger resolution, job definition resolution, and run persistence work against Postgres
- Job execution consumes resolved definition snapshots from the datastore
- Bootstrap/seed populates catalog and starter job so signed-in users receive the `Notion Place Inserter` template
- Runs and usage records are persisted in Postgres

## Out of scope

- Validation hardening (p4_pr03)
- Full observability and operator docs (p4_pr03)
- Secret reference backend migration (can remain env/local for Phase 4 V1)
- UI for run history or definition editing

## Dependencies

- Requires p4_pr01 (datastore schema and migrations).

---

## Manual validation steps (after implementation)

1. Start API and worker with Postgres-backed repos; confirm no startup errors.
2. Trigger a job via `POST /triggers/{user_id}/locations` and verify execution completes.
3. Query Postgres for `job_runs`, `stage_runs`, `pipeline_runs`, `step_runs`, `usage_records` and confirm records exist.
4. Restart container; confirm definitions and runs persist (durable).
5. Verify RLS: as a different user, confirm no access to another user's definitions or runs.

## Verification checklist

- [ ] All repository interfaces have Postgres implementations.
- [ ] API and worker use Postgres repos.
- [ ] Definitions and runs persist in Postgres.
- [ ] Snapshot-based execution is preserved.
- [ ] Bootstrap/seed populates catalog and starter job.
- [ ] RLS enforces tenant isolation.
