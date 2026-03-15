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

- [x] All repository interfaces have Postgres implementations.
- [x] API and worker use Postgres repos.
- [x] Definitions and runs persist in Postgres.
- [x] Snapshot-based execution is preserved.
- [x] Bootstrap/seed populates catalog and starter job.
- [ ] RLS enforces tenant isolation (schema in place; manual validation in p4_pr03).

## Implementation summary (2026-03-15)

- **Postgres repositories:** `postgres_repositories.py` (catalog, owner definitions, job graph), `postgres_run_repository.py` (RunRepository + lifecycle API)
- **ID mapping:** `id_mappings` table and `id_mapping.py` for deterministic UUIDv5 for nested run IDs (stage_run, pipeline_run, step_run, usage_record)
- **Bootstrap provisioning:** `BootstrapProvisioningService` interface, `PostgresBootstrapProvisioningService` with `seed_catalog_if_needed()` and `ensure_owner_starter_definitions(owner_user_id)`; `ENABLE_BOOTSTRAP_PROVISIONING` env switch
- **Runtime wiring:** `main.py` and `worker_main.py` use Postgres repos; locations route calls `ensure_owner_starter_definitions` before trigger resolution
- **Tests:** `test_postgres_run_repository.py`, `test_id_mapping.py`; locations and worker tests pass with new backend
