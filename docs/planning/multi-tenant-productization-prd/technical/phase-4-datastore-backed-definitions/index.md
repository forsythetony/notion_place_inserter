# Phase 4 Architecture: Datastore-Backed Definitions

## Status

- Not started
- Scope: replace YAML repositories with Postgres/Supabase-backed storage; durable definitions and runs; RLS-based tenant isolation

## Phase 4 PR Task Index

This folder breaks Phase 4 datastore migration into PR-sized stories. Complete them in order to avoid coupling runtime execution to unfinished schema or repository foundations.

### Required order

1. [`p4_pr01-datastore-schema-and-migrations.md`](./p4_pr01-datastore-schema-and-migrations.md)
2. [`p4_pr02-postgres-repositories-and-runtime-cutover.md`](./p4_pr02-postgres-repositories-and-runtime-cutover.md)
3. [`p4_pr03-validation-observability-tests-and-docs.md`](./p4_pr03-validation-observability-tests-and-docs.md)

### Why this sequence

- p4_pr01 establishes Postgres schema, migrations, indexes, and RLS baselines so repositories have a stable data model.
- p4_pr02 implements Postgres repository implementations and wires API/worker to them, replacing YAML adapters.
- p4_pr03 hardens validation, observability, tests, and operator docs for datastore-backed mode.

### Completion definition for this phase

Phase 4 is complete when p4_pr01–p4_pr03 are merged and validated together:

- definitions (connectors, targets, triggers, jobs, stages, pipelines, steps) are persisted in Postgres
- runs and usage records are persisted in Postgres
- RLS enforces owner-scoped access on all tenant tables
- job execution consumes resolved definition snapshots from the datastore
- edits are durable across container restarts and redeploys

### Manual validation and operator workflow

- **Bootstrap:** Start backend, sign in, confirm definitions load from Postgres.
- **Run:** Trigger a job run and verify execution uses snapshot; inspect run/usage records in the database.
- **Durable edits:** Edit a job definition, run it, restart container; confirm edits persist.

---

## Purpose

Phase 4 migrates the Phase 3 YAML-backed product model to Postgres/Supabase. Domain classes, service interfaces, validation rules, and execution semantics stay identical; only repository implementations and persistence strategy change.

### What stays identical (from Phase 3)

- domain classes
- service interfaces
- validation rules
- execution semantics
- step template catalog semantics

### What changes in Phase 4

- repository implementations (YAML → Postgres)
- secret reference backend (env/local alias → Vault or Supabase secrets)
- persistence/indexing strategy
- RLS enforcement on owner-scoped tables
- database constraints and migrations

## Recommended Postgres/Supabase shape

Use relational tables for identity, ownership, foreign keys, status, and sequencing. Use `jsonb` for flexible step config, request body schema, input bindings, target schema raw payload, definition snapshots, and usage metadata.

Recommended tables: `connector_templates`, `connector_instances`, `target_templates`, `data_targets`, `target_schema_snapshots`, `http_triggers`, `job_definitions`, `stage_definitions`, `pipeline_definitions`, `step_templates`, `step_instances`, `job_runs`, `stage_runs`, `pipeline_runs`, `step_runs`, `usage_records`, `app_limits`.

See Phase 3 index [Recommended Migration Path to Phase 4](../phase-3-yaml-backed-product-model/index.md#recommended-migration-path-to-phase-4) and [Recommended Postgres/Supabase shape](../phase-3-yaml-backed-product-model/index.md#recommended-postgressupabase-shape-for-phase-4) for full detail.
