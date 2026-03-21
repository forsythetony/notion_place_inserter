# Phase 4 Runtime Architecture Onboarding

## Purpose

This document explains the Phase 4 datastore cutover for a new engineer joining the project. It focuses on:

- what changed when the runtime moved from YAML-backed state to Postgres-backed state
- how definitions and runs are stored now
- what happens from `POST /triggers/{user_id}/locations` to a final page write in Notion
- where to look in the code when debugging each part of the flow

This is an architecture guide, not a product requirements doc.

## What Changed In Phase 4

Before Phase 4, the product model and runtime state were split across:

- YAML files for definitions
- YAML files for run history
- runtime conventions for resolving bootstrap data

After Phase 4, the runtime path is Postgres-backed:

- catalog definitions live in Postgres
- owner-scoped definitions live in Postgres
- run state lives in Postgres
- nested run records live in Postgres
- YAML is still used as a bootstrap source, but not as the runtime system of record

The design goal was to preserve the existing domain model and execution semantics while swapping the storage layer underneath it.

## Core Design Principles

### 1. Keep service interfaces stable

The execution services still work with the existing repository and service interfaces. The cutover mostly replaced repository implementations and startup wiring, rather than rewriting the orchestration model.

### 2. Keep bootstrap logic out of core runtime services

Bootstrap seeding and starter-definition provisioning are isolated behind `BootstrapProvisioningService`, so the runtime can eventually stop depending on YAML bootstrap input without having to rewrite repositories, route handlers, or execution services.

### 3. Preserve snapshot-driven execution

The worker still executes an immutable resolved snapshot, not live mutable definitions mid-run. This keeps runs reproducible even if definitions change after enqueue.

### 4. Preserve run-tree observability

We still record:

- job runs
- stage runs
- pipeline runs
- step runs
- usage records

The main difference is that the nested tables now use UUID primary keys, while the in-memory/domain runtime still generates readable string IDs for stage, pipeline, step, and usage records.

## Runtime Components

### API startup

`app/main.py` wires the application at startup:

- creates the Supabase client
- creates `PostgresRunRepository`
- creates the Postgres definition repositories
- creates `ValidationService`
- creates `TriggerService`, `TargetService`, `JobDefinitionService`, and `JobExecutionService`
- optionally runs bootstrap provisioning via `ENABLE_BOOTSTRAP_PROVISIONING`
- verifies the deterministic ID mapping contract at startup

### Worker startup

`app/worker_main.py` creates a parallel runtime graph for the worker:

- `SupabaseQueueRepository` for queue reads
- `PostgresRunRepository` for run state
- Postgres definition repositories for snapshot resolution
- `JobExecutionService` for the actual orchestration
- `run_worker_loop()` for async queue processing

### Route layer

`app/routes/locations.py` is the entrypoint for trigger invocations. It:

- authenticates the request
- validates the request body
- ensures the owner has starter definitions when bootstrap provisioning is enabled
- resolves the trigger and job snapshot
- creates the initial run record
- enqueues a worker message in async mode

### Queue worker

`app/queue/worker.py` is responsible for:

- polling the queue
- idempotency checks
- retry behavior
- transitioning run status through `queued -> running -> succeeded/failed`
- calling `JobExecutionService`
- archiving the queue message when done

### Execution engine

`app/services/job_execution/job_execution_service.py` orchestrates the actual workflow:

- stages run sequentially
- pipelines inside a stage run in parallel
- steps inside a pipeline run sequentially
- step outputs accumulate in the execution context
- final properties/icon/cover are written to Notion at the end

## Data Model Overview

The Phase 4 schema separates data into a few clear layers.

### 1. Platform catalog tables

These are shared definitions used across tenants:

- `connector_templates`
- `target_templates`
- `step_templates`

These are seeded from the YAML catalog at startup.

### 2. Owner-scoped definition tables

These define the actual runnable job graph for a user:

- `connector_instances`
- `data_targets`
- `target_schema_snapshots`
- `trigger_definitions`
- `job_definitions`
- `stage_definitions`
- `pipeline_definitions`
- `step_instances`
- `app_limits`

These are protected by owner scoping and intended to be durable across restarts.

### 3. Run-state tables

These capture execution history:

- `job_runs`
- `stage_runs`
- `pipeline_run_executions`
- `step_runs`
- `usage_records`

### 4. Mapping registry

`id_mappings` exists to bridge a mismatch between:

- runtime-generated string IDs like `run_uuid_stage_stage_research`
- database primary keys that must be UUIDs

It stores a write-once mapping from a domain/source ID to the UUID actually used in the database.

## Why `id_mappings` Exists

`job_runs.id` is already a UUID string generated as `run_id`, so it can be stored directly in `job_runs`.

But nested run IDs are generated as readable strings by the runtime:

- stage run: `"{run_id}_stage_{stage_id}"`
- pipeline run: `"{run_id}_pipeline_{pipeline_id}"`
- step run: `"{pipeline_run_id}_step_{step_id}"`
- usage record: generated string IDs like `usage_<hex>`

The nested Postgres tables use UUID primary keys, so the repository has to map these source IDs into UUIDs.

The chosen approach is:

1. Look up `(entity_type, source_id)` in `id_mappings`
2. If present, reuse the stored UUID
3. If absent, compute a deterministic UUIDv5
4. Insert the mapping row
5. Use that UUID for the nested table write

This gives us two benefits:

- the nested tables stay on UUID keys
- historical rows remain addressable even if the runtime only knows the original string ID

## Bootstrap And Provisioning Model

Bootstrap is deliberately split into two behaviors.

### Startup seed

At API startup, `PostgresBootstrapProvisioningService.seed_catalog_if_needed()` seeds:

- connector templates
- target templates
- step templates

This is idempotent and safe to run repeatedly.

### Lazy owner provisioning

At first trigger invocation for a user, `ensure_owner_starter_definitions(owner_user_id)` provisions owner-scoped starter rows if they do not exist:

- connector instances
- target
- trigger
- job graph

This means we do not pre-create starter definitions for every possible user up front.

To **re-import** the starter job and `/locations` trigger from bundled YAML after you change files on disk, use **`POST /management/bootstrap/reprovision-starter`** (authenticated) or follow the manual teardown steps — see [starter-job-reprovision-runbook.md](./starter-job-reprovision-runbook.md).

### Why this boundary matters

The route and worker do not parse YAML directly. They only call the bootstrap provisioning service. That keeps the bootstrap source replaceable later.

## End-To-End Run Flow

This section describes the main async path, which is the normal production path.

### Step 1. Request hits the endpoint

The request lands at:

- `POST /triggers/{user_id}/locations`
- handled by `app/routes/locations.py`

The route first:

- validates auth
- validates `keywords`
- checks whether async mode is enabled

### Step 2. Owner starter definitions are ensured

If bootstrap provisioning is enabled, the route calls:

- `bootstrap_provisioning_service.ensure_owner_starter_definitions(user_id)`

If this is the user's first run, the system provisions the starter trigger, target, connector instances, and job graph in Postgres.

After that, the route can resolve the user's trigger from Postgres like normal.

### Step 3. Trigger is resolved

The route normalizes the requested path to `/locations` and asks `TriggerService` to resolve it for the owner.

Under the hood, `PostgresTriggerRepository.get_by_path()` reads `trigger_definitions`.

If no trigger exists for that owner/path pair, the request fails.

### Step 4. Job snapshot is resolved

The route calls:

- `JobDefinitionService.resolve_for_run(trigger.job_id, user_id)`

This does three important things:

1. Loads the owner-scoped job graph from Postgres
2. Loads the trigger and target
3. Produces a resolved immutable snapshot plus `definition_snapshot_ref`

The snapshot contains:

- job graph
- trigger
- target
- active schema
- related targets used by some steps

This snapshot is what the worker will later execute.

### Step 5. Initial job run is persisted

Before queueing, the route calls:

- `PostgresRunRepository.create_job(...)`

This creates the top-level `job_runs` row with:

- `run_id` as `job_runs.id`
- owner
- job definition ID
- trigger ID
- target ID
- initial status
- trigger payload
- `definition_snapshot_ref`
- platform job ID used by the queue worker lifecycle

This is the first durable execution record.

### Step 6. Queue payload is sent

The route enqueues a message through `SupabaseQueueRepository.send(...)`.

The payload includes:

- `job_id`
- `run_id`
- `keywords`
- `job_definition_id`
- `definition_snapshot_ref`
- `owner_user_id`

The API then returns `{"status": "accepted", "job_id": ...}` to the caller.

At this point:

- the request has been accepted
- the run has been recorded
- the work has not necessarily executed yet

### Step 7. Worker reads the queue message

`run_worker_loop()` in `app/queue/worker.py` polls the queue.

When a message arrives, `_process_message()`:

- validates the payload
- checks whether the run is already terminal
- checks retry count and queue read count ceiling

This is the first idempotency barrier.

### Step 8. Worker marks the run as running

Before executing the pipeline, the worker persists:

- `job_runs.status = running`
- `job_runs.started_at`
- `job_runs.retry_count`

It also updates the run record and records a logical start event.

### Step 9. Worker resolves the snapshot again

The worker calls `_run_pipeline_sync()`, which resolves the job snapshot again using:

- `job_definition_id`
- `owner_user_id`

This keeps the worker storage-agnostic and snapshot-driven. The worker does not reconstruct logic manually from queue payload alone.

### Step 10. Execution service runs the job graph

`JobExecutionService.execute_snapshot_run()` drives the main orchestration.

Execution rules are:

- stages are sequential
- pipelines within a stage may be parallel
- steps within a pipeline are sequential

The service creates an `ExecutionContext` that holds:

- run metadata
- trigger payload
- per-step outputs
- cache values
- final property values
- icon/cover metadata
- service handles like Claude, Google Places, Notion, and usage accounting

### Step 11. Stage, pipeline, and step runs are persisted

As execution progresses, the service persists:

- `StageRun`
- `PipelineRun`
- `StepRun`

These runtime IDs are readable strings in memory, but `PostgresRunRepository` maps them to UUIDs for the nested Postgres tables.

That mapping happens in:

- `save_stage_run()`
- `save_pipeline_run()`
- `save_step_run()`
- `save_usage_record()`

Each of those uses `resolve_or_create_mapping()` for non-job nested IDs.

### Step 12. Step handlers build the final write payload

Each step handler receives:

- step config
- resolved inputs
- execution context
- full snapshot

Handlers do things like:

- optimize the query
- call Google Places
- cache intermediate results
- constrain values against the target schema
- select relations
- generate text with Claude
- accumulate property values
- prepare icon/cover metadata

They do not immediately write the Notion page. They mostly build up execution state.

### Step 13. Final Notion payload is assembled

After all stages complete, the execution service converts `ctx.properties` into a Notion payload via:

- `build_notion_properties_payload()`

This function uses the active schema to map internal property IDs to:

- external Notion property IDs
- correct property types
- proper value formatting

This is the bridge between internal orchestration output and the Notion API request shape.

### Step 14. The page is created in Notion

`NotionService.create_page()` performs the actual final write.

It builds the request:

- `parent.data_source_id`
- `properties`
- optional `icon`
- optional `cover`

If `DRY_RUN=1`, it logs and returns a synthetic result instead of calling Notion.

Otherwise it calls `pages.create(...)` on the Notion client and returns the created page payload.

This is the moment the run becomes a real Notion page.

### Step 15. Final usage and success state are persisted

After the page write:

- a Notion `usage_record` is written for `create_page`
- the worker marks the run as `succeeded`
- the worker archives the queue message
- success events are emitted for optional notifications

If anything fails along the way:

- the worker records failure state
- bounded retry logic may retry
- non-retriable database errors fail terminally
- final failure still archives the message after persistence attempts

## Read Path For Definitions

The most important definition read path for onboarding is:

1. `PostgresJobRepository.get_graph_by_id()`
2. `JobDefinitionService.resolve_for_run()`
3. `JobExecutionService.execute_snapshot_run()`

This is the core definition-to-execution pipeline.

`PostgresJobRepository.get_graph_by_id()` reconstructs a `JobGraph` from:

- `job_definitions`
- `stage_definitions`
- `pipeline_definitions`
- `step_instances`

That graph is then converted into a stable snapshot before execution.

## Where To Debug Specific Problems

### "The request reaches the API but no run exists"

Start with:

- `app/routes/locations.py`
- `app/repositories/postgres_run_repository.py`

Look at whether `create_job()` ran and whether `job_runs` got a row.

### "The trigger was not found"

Start with:

- `app/routes/locations.py`
- `app/services/postgres_seed_service.py`
- `app/repositories/postgres_repositories.py`

Most likely causes:

- owner starter definitions were never provisioned
- the trigger row is missing
- the path is not normalized to `/locations`

### "The worker got the message but the job did not execute"

Start with:

- `app/queue/worker.py`
- `app/worker_main.py`

Check:

- payload shape
- run idempotency status
- retry count
- queue archive behavior

### "The snapshot resolves but the Notion page is wrong"

Start with:

- `app/services/job_definition_service.py`
- `app/services/job_execution/job_execution_service.py`
- `app/services/job_execution/target_write_adapter.py`
- `app/services/notion_service.py`

That usually means:

- the target schema is stale or missing
- a step produced unexpected output
- property formatting did not match the Notion property type

### "Nested run rows look wrong or are missing"

Start with:

- `app/repositories/postgres_run_repository.py`
- `app/repositories/id_mapping.py`

Check:

- source ID generated by the execution service
- mapping row in `id_mappings`
- nested table FK UUID values

## Important Operational Callouts

### Mapping logic is a contract

The deterministic mapper namespace and version are effectively part of the data contract. Once live, changing them breaks recomputation for historical source IDs.

That is why we keep:

- a frozen namespace
- a frozen algorithm
- a write-once `id_mappings` table
- a startup consistency check

### The mapping table is the real source of truth

Even though mapping is deterministic, production should conceptually trust the persisted mapping row first. Deterministic recomputation is a fallback and a guardrail, not the only source of identity.

### Bootstrap is transitional infrastructure

YAML still exists as a bootstrap source. That does not mean YAML is still the runtime storage backend. It now acts more like seed data.

### Snapshot execution intentionally decouples queueing from live edits

If a job definition changes after enqueue, the worker should still execute a coherent snapshot for that run. This is a feature, not a bug.

### Current owner provisioning uses starter defaults

The lazy provisioning flow creates a starter target and starter connector instances. That is good enough for bootstrap, but onboarding engineers should treat it as scaffolding rather than the final long-term tenant-provisioning story.

## Suggested Mental Model

The simplest way to think about Phase 4 is:

- Postgres is now the runtime source of truth
- YAML is now a seed/input source
- the route creates durable run intent
- the worker executes that intent
- the execution service builds execution state
- the final state is written once to Notion
- every major lifecycle transition is persisted

If you keep that model in mind, most debugging sessions become much easier.

## Operator Runbook (Phase 4 Manual Validation)

### Prerequisites

- `envs/local.env` or equivalent with `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SECRET`, and optional `ENABLE_BOOTSTRAP_PROVISIONING=1`
- Local Supabase stack running (`make supabase-start`) or remote project linked

### 1. Run full test suite

```bash
python -m pytest tests/ -v
```

Expect all Phase 4 Postgres repo tests to pass (`test_postgres_repositories`, `test_postgres_run_repository`, `test_job_definition_service_postgres`).

### 2. Bootstrap and confirm definitions load

1. Start the API: `make run` or `make run-local`
2. Confirm startup logs show catalog seed and no mapping consistency errors
3. With `ENABLE_BOOTSTRAP_PROVISIONING=1`, the first `POST /triggers/{user_id}/locations` will provision owner starter definitions

### 3. Trigger a job and inspect runs

1. Start the worker: `make run-worker` (in a separate terminal)
2. Trigger: `make test-locations` or `curl -X POST -H "Authorization: $(SECRET)" -H "Content-Type: application/json" -d '{"keywords":"coffee shop"}' http://localhost:8000/triggers/bootstrap/locations`
3. Inspect runs in Postgres:
   - Local: `make show-runs-db` or Supabase Studio (`make supabase-dashboard`)
   - Query: `SELECT id, owner_user_id, job_id, status, platform_job_id, created_at FROM job_runs ORDER BY created_at DESC LIMIT 20`

### 4. Log correlation for debugging

Key log patterns in datastore mode:

- `locations_enqueued | job_id=... run_id=...` — request accepted
- `postgres_run_event | run_id=... event_type=pipeline_started` — worker began execution
- `postgres_run_event | run_id=... event_type=pipeline_succeeded` — execution completed
- `worker_persist_*_failed | job_id=... run_id=...` — persistence failure

### 5. RLS and tenant isolation

- RLS policies enforce `auth.uid() = owner_user_id` on owner-scoped tables
- To verify: use Supabase Studio with different auth contexts, or run queries as different users
- See `supabase/migrations/20260315100000_phase4_pr01_datastore_schema.sql` for policy definitions

### 6. Deprecated tooling

- `make show-runs` — deprecated; Phase 4 runs are in Postgres. Use `make show-runs-db` or Supabase Studio.
