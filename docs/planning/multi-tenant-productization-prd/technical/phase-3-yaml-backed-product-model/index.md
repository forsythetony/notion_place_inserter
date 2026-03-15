# Phase 3 Architecture: YAML-Backed Product Model

## Status

- Complete: p3_pr01-p3_pr08 (2026-03-15)
- Scope: define the canonical product model and back it with local YAML repositories before moving definitions into Postgres/Supabase

## Phase 3 PR Task Index

This folder breaks Phase 3 YAML-backed product model into PR-sized stories. Complete them in order to avoid coupling runtime execution to unfinished domain and repository foundations.

### Required order

1. [`p3_pr01-domain-entities-and-ownership-model.md`](./p3_pr01-domain-entities-and-ownership-model.md)
2. [`p3_pr02-repository-interfaces-and-yaml-layout.md`](./p3_pr02-repository-interfaces-and-yaml-layout.md)
3. [`p3_pr03-yaml-catalog-and-bootstrap-seed.md`](./p3_pr03-yaml-catalog-and-bootstrap-seed.md)
4. [`p3_pr04-definition-validation-service.md`](./p3_pr04-definition-validation-service.md)
5. [`p3_pr07-trigger-target-and-schema-services.md`](./p3_pr07-trigger-target-and-schema-services.md)
6. [`p3_pr05-job-definition-resolution-and-snapshotting.md`](./p3_pr05-job-definition-resolution-and-snapshotting.md)
7. [`p3_pr06-runtime-wiring-to-yaml-backed-definitions.md`](./p3_pr06-runtime-wiring-to-yaml-backed-definitions.md)
8. [`p3_pr08-runs-usage-observability-and-docs.md`](./p3_pr08-runs-usage-observability-and-docs.md)

### Why this sequence

- p3_pr01 establishes domain classes and ownership metadata so all later work uses stable product-model types.
- p3_pr02 defines repository interfaces and YAML layout so storage adapters have a clear contract.
- p3_pr03 seeds the catalog and bootstrap `Notion Place Inserter` template for authenticated users.
- p3_pr04 adds validation so saves enforce ID resolution, sequencing, limits, and terminal step rules (`Cache Set` or `Property Set`).
- p3_pr07 wires trigger, target, and schema services to YAML repositories so resolution can fetch referenced entities.
- p3_pr05 implements job-definition resolution and snapshotting for execution (depends on trigger/target/schema repos).
- p3_pr06 migrates runtime from code-bound registries to YAML-backed definitions.
- p3_pr08 adds runs/usage records and hardens tests/docs for manual validation.

### Completion definition for this phase

Phase 3 is complete when p3_pr01–p3_pr08 are merged and validated together:

- every signed-in user receives the same `Notion Place Inserter` starter definition from bundled YAML
- job execution consumes resolved definition snapshots, not live definitions
- edits are container-local and explicitly non-durable across Render restarts
- domain classes and service interfaces are storage-agnostic and ready for Phase 4 Postgres migration

### Manual validation and operator workflow

- **Bootstrap:** Start backend, sign in, confirm `Notion Place Inserter` job loads from bundled YAML.
- **Run:** Trigger a job run and verify execution uses snapshot; inspect run/usage records.
- **Ephemeral edits:** Edit a job definition, run it, restart container; confirm edits are lost and bootstrap template is restored.

---

## Purpose

Phase 3 converts the current code-assembled job system into a real serialized product model.

Canonical hierarchy for this document:

- `Job -> Stage -> Pipeline -> PipelineStep`

Terminology rule:

- `Job` is the top-level orchestration object
- `Stage` is the sequential grouping within a job
- `Pipeline` is the mid-level container within a stage
- `PipelineStep` is the ordered unit within a pipeline

In places where the current codebase still uses names like `GlobalPipeline`, this document treats that as an implementation detail from the current runtime rather than the canonical product-model term.

The key rule for this phase is simple:

- the same domain data classes should be used in Phase 3 and Phase 4
- the same service-layer orchestration should be used in Phase 3 and Phase 4
- only the repository implementation should change between phases
- in Phase 3, repositories read/write YAML
- in Phase 4, repositories read/write Postgres/Supabase

This keeps the YAML-to-database migration thin and prevents us from baking product semantics into Python registries that later need to be unwound.

## Phase 3 bootstrap behavior

For this phase, the test product should be encoded directly in checked-in YAML as the `Notion Place Inserter` template.

Phase 3 runtime behavior should be:

- every signed-in user receives the same `Notion Place Inserter` starter definition
- that starter definition is loaded from bundled YAML in the repository
- any user edits in this phase are stored only on the local filesystem of the running Render container
- those edits are explicitly non-durable and do not survive container restarts or redeploys

This is intentional for Phase 3. The goal is to validate the serialized product model, repository boundaries, and editing flow without yet introducing durable per-user definition persistence.

The canonical domain model should still retain owner-scoped IDs and ownership metadata so the Phase 4 migration to durable datastore-backed definitions remains thin.

## Existing Phase 3 Mentions

Phase 3 was already scoped at a high level in the PRD and technical index:

- the PRD defines Phase 3 as the point where triggers, targets, jobs, stages, pipelines, and steps become YAML-backed instead of code-backed
- the technical docs index already reserves this folder for the Phase 3 model

This document is the canonical detailed architecture for that phase.

## Current-State Findings

The current implementation already has useful execution primitives, but the product model is still mostly assembled in code.

### What already maps well

- `app/pipeline_lib/core.py` already preserves the right execution layers in code: `GlobalPipeline`, `Stage`, `Pipeline`, and `PipelineStep`, where `GlobalPipeline` is the current code name for the top-level job-like abstraction
- `app/pipeline_lib/orchestration.py` already enforces the desired runtime semantics:
  - stages run sequentially
  - pipelines inside a parallel stage fan out concurrently
  - steps run sequentially inside a pipeline
- `app/pipeline_lib/context.py` already acts as a run-scoped artifact/cache container
- `app/services/supabase_run_repository.py` already proves the repository pattern is workable for runtime persistence

### What is still too code-bound

- `app/app_global_pipelines/__init__.py` hard-codes the available top-level job-like orchestrators
- `app/app_global_pipelines/places_to_visit.py` hard-codes stage order and pipeline composition
- `app/custom_pipelines/__init__.py` maps Notion property names directly to Python classes
- `app/services/places_service.py` always resolves `places_global_pipeline`, which is the current code-level top-level job-like runtime object
- `app/services/notion_service.py` and `app/services/schema_cache.py` fetch live schema, but there is no persisted product-level target/schema model yet
- Trigger invocation uses the user-scoped endpoint `POST /triggers/{user_id}/{path}` (e.g. `POST /triggers/{user_uuid}/locations`) so Tony's `/locations` does not conflict with Patrick's; trigger definitions are persisted in YAML

### Architecture implication

Phase 3 should preserve the runtime abstractions but move the following concerns into persisted definitions:

- trigger definitions
- target definitions
- target schema snapshots
- job definitions
- stage definitions
- pipeline definitions
- step template definitions
- configured step instances
- connector templates and user-owned connector instances

## Design Principles

1. Stable IDs over display names. Product objects should reference stable IDs, not raw Notion property names.
2. Templates and configured instances are separate. Marketplace definitions and user-configured copies must be modeled independently.
3. Targets and schemas are global resources. They do not live inside any one job.
4. Execution consumes a snapshot. A run should execute against a resolved definition snapshot, not a moving target.
5. YAML is an implementation detail of the repository. The domain model should not care whether backing storage is YAML or Postgres.
6. Limits must exist in the model. Abuse prevention is not optional.
7. Multi-tenancy must be visible in the model now, even though YAML is local.
8. Secrets are never first-class plaintext config values. Connector instances should store secret references, not raw secrets.

## Proposed Layering

### Domain objects

Pure data classes that define the product model:

- `ConnectorTemplate`
- `ConnectorInstance`
- `TargetTemplate`
- `DataTarget`
- `TargetSchemaSnapshot`
- `TriggerDefinition`
- `JobDefinition`
- `StageDefinition`
- `PipelineDefinition`
- `StepTemplate`
- `StepInstance`
- `AppLimits`
- `JobRun`
- `StageRun`
- `PipelineRun`
- `StepRun`
- `UsageRecord`

### Repositories

Storage adapters with the same interface in both phases:

- `ConnectorTemplateRepository`
- `ConnectorInstanceRepository`
- `TargetRepository`
- `TargetSchemaRepository`
- `TriggerRepository`
- `JobRepository`
- `StepTemplateRepository`
- `RunRepository`
- `AppConfigRepository`

Phase 3 implementations:

- `YamlConnectorTemplateRepository`
- `YamlConnectorInstanceRepository`
- `YamlTargetRepository`
- `YamlTargetSchemaRepository`
- `YamlTriggerRepository`
- `YamlJobRepository`
- `YamlStepTemplateRepository`
- `YamlRunRepository`
- `YamlAppConfigRepository`

Phase 4 implementations:

- `PostgresConnectorTemplateRepository`
- `PostgresConnectorInstanceRepository`
- `PostgresTargetRepository`
- `PostgresTargetSchemaRepository`
- `PostgresTriggerRepository`
- `PostgresJobRepository`
- `PostgresStepTemplateRepository`
- `PostgresRunRepository`
- `PostgresAppConfigRepository`

### Services

Business logic that should remain unchanged when storage moves from YAML to Postgres:

- `TriggerService`
- `TargetService`
- `SchemaSyncService`
- `ConnectorService`
- `JobDefinitionService`
- `JobExecutionService`
- `UsageAccountingService`
- `ValidationService`

## Core Product Entities

## Ownership Model

Every persisted object should carry ownership metadata now, even in YAML:

- `owner_user_id`
- optional future `workspace_id`
- `visibility`

Expected `visibility` values:

- `platform` for marketplace templates
- `owner` for tenant-scoped configured resources

This gives us a clean path to Postgres row-level security later.

## Connector Templates and Connector Instances

### Why both are needed

External systems need two layers:

- a canonical marketplace definition
- a user-owned configured/authenticated instance

Examples:

- canonical `notion_oauth_workspace` connector template
- Tony's configured Notion connection
- Patrick's configured Notion connection

These must never collapse into one object.

### `ConnectorTemplate`

Represents a platform-owned marketplace entry.

Suggested fields:

- `id`
- `slug`
- `display_name`
- `connector_type`
- `provider`
- `auth_strategy`
- `capabilities`
- `config_schema`
- `secret_schema`
- `status`

Examples of `capabilities`:

- `fetch_target_schema`
- `create_target_record`
- `http_trigger_ingress`
- `google_places_search`
- `claude_text_generation`

### `ConnectorInstance`

Represents a user-owned configured connector.

Connector instances are owner-scoped resources, not pipeline-scoped resources. A user configures a connector once, then reuses that configured instance across multiple jobs, triggers, targets, and pipelines as needed. A connector instance can be refreshed, revalidated, reconfigured, or inspected independently of any specific job definition.

Suggested fields:

- `id`
- `owner_user_id`
- `connector_template_id`
- `display_name`
- `status`
- `config`
- `secret_ref`
- `last_validated_at`
- `last_error`

Important note:

- `secret_ref` should point to an environment/local secret alias in Phase 3 and to Vault/secret storage in Phase 4
- the YAML should not become a plaintext credential dump
- a user should never need to re-authenticate or recreate a connector instance just because they are building a new job

## Target Templates, Data Targets, and Schema Snapshots

### `TargetTemplate`

Platform-owned metadata for a target type.

For V1, there is only one:

- `notion_database`

Suggested fields:

- `id`
- `slug`
- `display_name`
- `target_kind`
- `required_connector_template_id`
- `supports_schema_snapshots`
- `property_types_supported`

### `DataTarget`

User-owned global resource representing a specific target instance.

For V1 this is a specific Notion database node.

Data targets are owner-scoped reusable resources. They live outside any individual job or pipeline and can be referenced by multiple jobs over time. A target can be refreshed, reconfigured, inspected, or schema-synced without modifying the jobs that use it.

Suggested fields:

- `id`
- `owner_user_id`
- `target_template_id`
- `connector_instance_id`
- `display_name`
- `external_target_id`
- `status`
- `active_schema_snapshot_id`
- `target_settings`
- `created_at`
- `updated_at`

Important behavior:

- this object lives outside any job
- multiple jobs can reference the same target
- target-level rules can exist independently of any one job
- this decoupling is intentional so target setup and target maintenance do not require pipeline edits

### `TargetSchemaSnapshot`

Represents a fetched schema at a point in time.

Suggested fields:

- `id`
- `owner_user_id`
- `data_target_id`
- `version`
- `fetched_at`
- `is_active`
- `source_connector_instance_id`
- `properties`
- `raw_source_payload`

### `TargetSchemaProperty`

Each schema snapshot contains properties with stable IDs.

Suggested fields:

- `id`
- `external_property_id`
- `name`
- `normalized_slug`
- `property_type`
- `required`
- `readonly`
- `options`
- `metadata`

For `select` and `multi_select`, `options` should persist all currently known values.

This is important for:

- `AI Constrain Values`
- property-level guardrails
- historical reproducibility
- future schema diffing

### Global target-level property rules

The target model should support global property rules outside any job.

Examples:

- property is locked and can never be set by pipelines
- property allows only existing options
- property allows AI-suggested options
- property should always be treated as no-op

Suggested shape:

- `property_rules` on `DataTarget`, keyed by schema property ID

## Trigger Definitions

For V1, only HTTP triggers are supported.

### `TriggerDefinition`

Suggested fields:

- `id`
- `owner_user_id`
- `trigger_type`
- `display_name`
- `path`
- `method`
- `request_body_schema`
- `status`
- `job_id`
- `auth_mode`
- `created_at`
- `updated_at`

Rules:

- V1 supports `POST` only
- The full HTTP path is `POST /triggers/{owner_user_id}/{path}`; path is the segment after user_id (e.g. `locations`)
- path must be unique within the owning tenant namespace
- one trigger points to one job in V1
- request body shape should be stored in a JSON-schema-like structure, even if YAML is the container format

When invoked, the trigger emits an initial signal:

- `trigger.payload`

## Jobs, Stages, Pipelines, and Steps

## `JobDefinition`

Represents the top-level executable graph.

This is the canonical top-level orchestration object in the product model. The word `pipeline` should not be used for this layer.

Suggested fields:

- `id`
- `owner_user_id`
- `display_name`
- `trigger_id`
- `target_id`
- `status`
- `stage_ids`
- `default_run_settings`
- `created_at`
- `updated_at`

Rules:

- a job has one or more stages
- stages run sequentially
- jobs reference targets globally rather than embedding target definitions

## `StageDefinition`

Suggested fields:

- `id`
- `job_id`
- `display_name`
- `sequence`
- `pipeline_ids`
- `pipeline_run_mode`

Defaults:

- `pipeline_run_mode: parallel`

The model should allow `sequential` later, but V1 behavior matches the current runtime:

- stages are sequential
- pipelines inside a stage run in parallel by default

## `PipelineDefinition`

Suggested fields:

- `id`
- `stage_id`
- `display_name`
- `sequence`
- `step_ids`
- `purpose`

Pipelines contain ordered steps that execute sequentially.

## Step templates and configured step instances

### `StepTemplate`

Platform-owned reusable step definition.

Suggested fields:

- `id`
- `slug`
- `display_name`
- `step_kind`
- `description`
- `input_contract`
- `output_contract`
- `config_schema`
- `runtime_binding`
- `category`
- `status`

This replaces Python-only registries as the catalog layer.

`input_contract` may optionally include `query_schema`, a machine-readable description of what an ideally shaped input looks like for that step. Not all step templates need to define one. It is only meaningful for steps that benefit from receiving pre-shaped input from an upstream optimizer.

### `StepInstance`

Tenant-owned configured use of a step inside a pipeline.

Step instances are both owner-scoped and pipeline-scoped. They are not reusable owner-level resources. `pipeline_id` is a hard scoping boundary, not a convenience foreign key: a step instance has no meaningful existence outside its pipeline.

Suggested fields:

- `id`
- `pipeline_id`
- `step_template_id`
- `display_name`
- `sequence`
- `input_bindings`
- `config`
- `failure_policy`

This is where template-vs-instance separation matters for steps:

- the template defines what kind of step exists in the gallery
- the instance stores how that step is configured inside one specific pipeline
- if two pipelines use the same step template, they create two separate step instances
- there is no concept of a shared or reusable step instance across pipelines

## Signal and binding model

The current implementation uses a mutable context dict. Phase 3 should make the serialization contract explicit.

Each trigger and step should expose named outputs defined by the trigger or step template. Later steps bind inputs directly to those outputs by name.

Suggested binding shapes:

- `signal_ref`: reference a trigger or step output
- `cache_key_ref`: read from the run-scoped shared cache
- `static_value`: inline literal
- `target_schema_ref`: reference target schema metadata

Examples:

- `trigger.payload`
- `step.optimize_query.optimized_query`
- `cache.google_places_response`
- `target_schema.tags.options`

This keeps the runtime flexible without forcing the YAML model to mirror the raw mutable context object.

## Initial Step Catalog

The following step templates should exist in the initial catalog.

### 1. Optimize Input (Claude)

Purpose:

- reshape one or more input signals for downstream consumption

Suggested config:

- `prompt`
- `input_signal_refs`
- `linked_step_id`
- `include_target_query_schema`

Important behavior:

- `Optimize Input` is intentionally generic, but it may become aware of its downstream target when `linked_step_id` is configured
- when the linked step's template exposes `input_contract.query_schema`, the UI may expose `include_target_query_schema`
- when `include_target_query_schema` is enabled, the resolved downstream `query_schema` is injected into the runtime Claude prompt so the model shapes its output to match that schema
- if the linked step does not advertise `input_contract.query_schema`, `include_target_query_schema` is not available and no schema is injected

### Optimize Input downstream-awareness rule

This `linked_step_id` plus `input_contract.query_schema` mechanism is the only inter-step awareness supported in Phase 3.

Steps do not otherwise negotiate contracts with each other, infer each other's internal behavior, or participate in broader contract-matching logic. The only allowed pattern in this phase is:

- `Optimize Input` targets one subsequent step via `linked_step_id`
- that subsequent step's template may advertise `input_contract.query_schema`
- `Optimize Input` may optionally include that schema in its runtime prompt when `include_target_query_schema` is enabled

### 2. Google Places API Lookup

Purpose:

- perform a Google Places lookup from an incoming search value

Suggested config:

- `connector_instance_id`
- `query_input_ref`
- `return_mode`
- `fetch_details_if_needed`

Example `input_contract`:

```yaml
input_contract:
  fields:
    query:
      type: string
      required: true
  query_schema:
    type: string
    description: Optimized Google Places text query
    guidance:
      - Use a concise plain-language place query
      - Prefer place name plus city/region when available
      - Avoid explanatory prose, markdown, or extra labels
      - Return a single query string, not a JSON object
    examples:
      - "Stone Arch Bridge Minneapolis MN"
      - "Cafe Mogador Williamsburg Brooklyn NY"
```

Outputs:

- `search_response`
- `selected_place`

### 3. AI Constrain Values (Claude)

Purpose:

- select zero or more values from an allowed list, with optional suggestion behavior

Suggested config:

- `input_signal_refs`
- `allowable_values_source`
- `max_suggestible_values`
- `allowable_value_eagerness`
- `max_output_values`
- `model`

`allowable_values_source` should support:

- static list
- target schema property options
- step output that resolves to a list

### 4. Cache Set

Purpose:

- store a value into the run-scoped shared cache for later stages and pipelines

Suggested config:

- `cache_key`
- `value_ref`

### 5. Cache Get

Purpose:

- retrieve a previously stored cache value

Suggested config:

- `cache_key`

### 6. AI Select Relation

Purpose:

- use AI to select the best relation from a related database by key lookup

Suggested config:

- `related_db` (required): data_target_id of the related database
- `key_lookup` (default: title): property to use for matching (e.g. title, Name)
- `prompt` (optional): additional instructions for the AI selection

Input: `source_value` or `value` (e.g. cached Google Place record)

Outputs:

- `selected_page_pointer`: `{"id": "page-uuid"}` or None
- `selected_relation`: `[{"id": "page-uuid"}]` or `[]` (Notion-ready format)

When no confident match is found, returns empty relation so the run continues.

### 7. Property Set

Purpose:

- write a value to a specific target schema property

Suggested config:

- `data_target_id`
- `schema_property_id`
- `value_ref`

Rules:

- any pipeline must terminate in either `Cache Set` or `Property Set`
- when a pipeline terminates in `Property Set`, it must reference a real target schema property
- this should be validated on save and enforced at execution time

### 8. Utility: Extract Target Property Options

Purpose:

- return the current option list for a target property

Suggested config:

- `data_target_id`
- `schema_property_id`

This step is optional in the UX, but the architecture should support it because it makes schema-driven AI steps cleaner and less magical.

## Execution Model

## Run-scoped cache

Phase 3 should keep a run-scoped shared cache because it matches the current runtime and the desired job semantics.

Suggested behavior:

- writable by any pipeline step
- readable by all downstream stages
- isolated to a single run
- never shared across jobs or users

Examples:

- research stage stores `google_places_response`
- later property-setting pipelines read from that key

## Definition snapshotting

Runs should execute against a resolved snapshot containing:

- job definition
- referenced stage, pipeline, and step definitions
- trigger definition
- target definition
- active target schema snapshot

This snapshot can be persisted as YAML in Phase 3 and as structured DB records plus snapshot JSONB in Phase 4.

That is important for:

- debugging
- replayability
- historical correctness when target schemas later change

## Terminal target write behavior

The target write should be modeled as an explicit terminal operation, not as an accidental side effect.

For Notion V1:

- the final resolved property payload is created from `Property Set` outputs
- non-property target metadata such as icon/cover should also be modeled explicitly as target write inputs

This avoids keeping important write behavior in hidden runtime side channels.

## Non-Property Target Outputs

The current runtime treats icon and cover as special outputs outside the generic property map.

Phase 3 should model those explicitly.

Suggested options:

1. Treat them as reserved target metadata fields on the target template.
2. Add explicit step templates like `Page Icon Set` and `Page Cover Set`.

Recommendation:

- represent them as reserved target metadata bindings in the target template so they serialize cleanly without pretending they are ordinary Notion properties

## Limits and Abuse Prevention

Limits should live in a globally readable application configuration object and optionally be overridable per user tier later.

### `AppLimits`

Suggested fields:

- `max_stages_per_job`
- `max_pipelines_per_stage`
- `max_steps_per_pipeline`

Validation should happen:

- in the service layer on save
- again in the execution layer defensively

The Phase 4 database should also add check/trigger-based guardrails where practical.

## Observability and Metrics

The data model should include first-class run and usage records.

### `JobRun`

Suggested fields:

- `id`
- `owner_user_id`
- `job_id`
- `trigger_id`
- `target_id`
- `status`
- `trigger_payload`
- `definition_snapshot_ref`
- `started_at`
- `completed_at`
- `error_summary`

### `StageRun`

Suggested fields:

- `id`
- `job_run_id`
- `stage_id`
- `status`
- `started_at`
- `completed_at`

### `PipelineRun`

Suggested fields:

- `id`
- `stage_run_id`
- `pipeline_id`
- `status`
- `started_at`
- `completed_at`

### `StepRun`

Suggested fields:

- `id`
- `pipeline_run_id`
- `step_id`
- `step_template_id`
- `status`
- `input_summary`
- `output_summary`
- `started_at`
- `completed_at`
- `error_summary`

### `UsageRecord`

Suggested fields:

- `id`
- `job_run_id`
- optional `step_run_id`
- `usage_type`
- `provider`
- `metric_name`
- `metric_value`
- `metadata`

Initial `usage_type` values:

- `llm_tokens`
- `external_api_call`

Examples:

- Claude prompt tokens
- Claude completion tokens
- Google Places search call count
- Notion schema fetch call count
- Notion page create call count

## Multi-Tenancy and Isolation

Even in YAML, the model must preserve tenant boundaries.

Rules:

- marketplace templates are platform-owned
- connector instances, targets, schema snapshots, triggers, jobs, and runs are owner-scoped
- one user must never resolve another user's connector instance, target schema, trigger, or run history

Phase 3 implementation note:

- although the canonical model is owner-scoped, the initial authenticated experience may bootstrap every signed-in user from the same checked-in `Notion Place Inserter` YAML template
- edits made in this phase are container-local and ephemeral, so Phase 3 should not be treated as durable tenant persistence
- the owner-scoped shape still matters because it defines the correct service and repository contracts for Phase 4

Recommended ownership strategy for V1:

- use `owner_user_id` everywhere for tenant-owned objects
- leave room for `workspace_id` later without changing object identity semantics

Phase 4 database enforcement:

- Postgres RLS on every owner-scoped table
- policies based on `auth.uid()`
- indexes on owner columns and common foreign keys

## YAML Repository Layout

The repository interface should hide the file layout, but we still need a practical on-disk structure.

Recommended layout:

```text
product_model/
  bootstrap/
    jobs/
      notion_place_inserter.yaml
  catalog/
    connector_templates/
      notion_oauth_workspace.yaml
      google_places_api.yaml
      claude_api.yaml
    target_templates/
      notion_database.yaml
    step_templates/
      optimize_input_claude.yaml
      google_places_lookup.yaml
      ai_constrain_values_claude.yaml
      cache_set.yaml
      cache_get.yaml
      property_set.yaml
      extract_target_property_options.yaml
  tenants/
    <owner_user_id>/
      app_config.yaml
      connector_instances/
        *.yaml
      targets/
        *.yaml
      target_schema_snapshots/
        *.yaml
      triggers/
        *.yaml
      jobs/
        *.yaml
      runs/
        *.yaml
```

Guidelines:

- the bundled `bootstrap/jobs/notion_place_inserter.yaml` file is the shared Phase 3 starter template for authenticated users
- one object per file for user-owned resources
- immutable schema snapshots once written
- append-only run records
- stable IDs in filenames where possible
- writes on Render are container-local only and are expected to disappear on restart

## Example YAML Shapes

## Example target

```yaml
kind: data_target
id: target_places_to_visit
owner_user_id: user_tony
target_template_id: target_template_notion_database
connector_instance_id: connector_instance_notion_tony_main
display_name: Places to Visit
external_target_id: 9592d56b-899e-440e-9073-b2f0768669ad
status: active
active_schema_snapshot_id: schema_places_to_visit_v3
target_settings:
  create_behavior: create_page
property_rules:
  prop_tags:
    locked: false
    allow_existing_values_only: false
  prop_source:
    locked: true
    lock_behavior: no_op
```

## Example schema snapshot

```yaml
kind: target_schema_snapshot
id: schema_places_to_visit_v3
owner_user_id: user_tony
data_target_id: target_places_to_visit
version: 3
fetched_at: "2026-03-14T18:45:00Z"
is_active: true
properties:
  - id: prop_title
    external_property_id: title
    name: Title
    normalized_slug: title
    property_type: title
    required: true
    readonly: false
    options: []
  - id: prop_tags
    external_property_id: tags_123
    name: Tags
    normalized_slug: tags
    property_type: multi_select
    required: false
    readonly: false
    options:
      - id: opt_history
        name: History
      - id: opt_landmark
        name: Landmark
```

## Example job

```yaml
kind: job_definition
id: job_place_ingest
owner_user_id: user_tony
display_name: Place Ingest
trigger_id: trigger_http_places_ingest
target_id: target_places_to_visit
status: active
stage_ids:
  - stage_research
  - stage_property_setting
stages:
  - id: stage_research
    display_name: Research
    sequence: 1
    pipeline_run_mode: parallel
    pipelines:
      - id: pipeline_research
        display_name: Research Pipeline
        sequence: 1
        steps:
          - id: step_optimize_query
            step_template_id: step_template_optimize_input_claude
            sequence: 1
            input_bindings:
              query:
                signal_ref: trigger.payload.raw_input
            config:
              prompt: Rewrite this input into an optimized Google Places query.
              linked_step_id: step_google_places_lookup
              include_target_query_schema: true
          - id: step_google_places_lookup
            step_template_id: step_template_google_places_lookup
            sequence: 2
            input_bindings:
              query:
                signal_ref: step.step_optimize_query.optimized_query
            config:
              connector_instance_id: connector_instance_google_places_default
              fetch_details_if_needed: true
          - id: step_cache_places
            step_template_id: step_template_cache_set
            sequence: 3
            input_bindings:
              value:
                signal_ref: step.step_google_places_lookup.search_response
            config:
              cache_key: google_places_response
  - id: stage_property_setting
    display_name: Property Setting
    sequence: 2
    pipeline_run_mode: parallel
    pipelines:
      - id: pipeline_tags
        display_name: Set Tags
        sequence: 1
        steps:
          - id: step_cache_get_places
            step_template_id: step_template_cache_get
            sequence: 1
            config:
              cache_key: google_places_response
          - id: step_constrain_tags
            step_template_id: step_template_ai_constrain_values_claude
            sequence: 2
            input_bindings:
              source_value:
                signal_ref: step.step_cache_get_places.value
            config:
              allowable_values_source:
                target_schema_ref:
                  data_target_id: target_places_to_visit
                  schema_property_id: prop_tags
                  field: options
              max_suggestible_values: 2
              allowable_value_eagerness: 3
              max_output_values: 3
          - id: step_property_set_tags
            step_template_id: step_template_property_set
            sequence: 3
            input_bindings:
              value:
                signal_ref: step.step_constrain_tags.selected_values
            config:
              data_target_id: target_places_to_visit
              schema_property_id: prop_tags
```

## Validation Rules

The service layer should validate at save time.

Required initial rules:

- referenced IDs must exist and belong to the same owner unless platform-owned
- a job must have at least one stage
- a stage must have at least one pipeline
- a pipeline must have at least one step
- stage sequences must be unique within a job
- pipeline sequences must be unique within a stage
- step sequences must be unique within a pipeline
- trigger paths must be unique per owner
- each pipeline must terminate with either `Cache Set` or `Property Set`
- if the terminal step is `Property Set`, it must reference a real target schema property on the job's target
- step input bindings must resolve to known signal/cache/schema sources
- object counts must not exceed configured limits

## Recommended Migration Path to Phase 4

Phase 4 should not redesign the model. It should only replace YAML repositories with Postgres repositories and add database-native enforcement.

### What should stay identical

- domain classes
- service interfaces
- validation rules
- execution semantics
- step template catalog semantics

### What changes in Phase 4

- repository implementations
- secret reference backend
- persistence/indexing strategy
- RLS enforcement
- database constraints and migrations

## Recommended Postgres/Supabase shape for Phase 4

Use relational tables for identity, ownership, foreign keys, status, and sequencing.

Use `jsonb` for:

- flexible step config
- request body schema
- input binding payloads
- target schema raw source payload
- definition snapshots
- usage metadata

Do not over-compress the whole product model into a single opaque blob. The database should still preserve relational ownership and queryability.

Recommended future tables:

- `connector_templates`
- `connector_instances`
- `target_templates`
- `data_targets`
- `target_schema_snapshots`
- `http_triggers`
- `job_definitions`
- `stage_definitions`
- `pipeline_definitions`
- `step_templates`
- `step_instances`
- `job_runs`
- `stage_runs`
- `pipeline_runs`
- `step_runs`
- `usage_records`
- `app_limits`

## Relevant Postgres and Supabase Guidance

These references align with the Phase 4 storage direction:

- PostgreSQL recommends `jsonb` for most structured document-style data because it is stored in a decomposed binary format and supports indexing: [JSON Types](https://www.postgresql.org/docs/15/datatype-json.html)
- PostgreSQL check constraints are the right primitive for some hard guardrails around stored data: [Constraints](https://www.postgresql.org/docs/15/ddl-constraints.html)
- Supabase recommends RLS policies based on `auth.uid()` for user-scoped access control: [Row Level Security](https://supabase.com/docs/learn/auth-deep-dive/auth-row-level-security)
- Supabase documents `jsonb` as appropriate for flexible payloads while still cautioning against replacing proper relational modeling entirely: [Managing JSON and unstructured data](https://supabase.com/docs/guides/database/json)
- Supabase also exposes `pg_jsonschema`, which is relevant if we want database-level validation for stored step config or request body schemas later: [pg_jsonschema](https://supabase.com/docs/guides/database/extensions/pg_jsonschema)

## Explicit Decisions

1. The canonical product model will separate templates from configured instances.
2. Targets and schema snapshots are global owner-scoped resources, not job-local config.
3. YAML repositories are a temporary storage backend, not a separate architecture.
4. Runs execute against resolved definition snapshots.
5. Limits are first-class application configuration, not ad hoc constants.
6. Multi-tenancy is modeled now with `owner_user_id`, then enforced in Postgres with RLS in Phase 4.
7. Non-property target outputs such as icon and cover are modeled explicitly rather than hidden in runtime-only context keys.
8. The canonical execution hierarchy is `Job -> Stage -> Pipeline -> PipelineStep`; `pipeline` never refers to the top-level orchestration layer in this document.
9. Phase 3 ships with a checked-in `Notion Place Inserter` YAML starter template for all signed-in users, and any edits are explicitly ephemeral across Render container restarts.

## Open Questions to Resolve During Implementation

1. Should icon/cover use dedicated step templates or reserved target metadata bindings only?
2. Should trigger request body schemas use full JSON Schema or a constrained subset for easier UI editing?
3. Do we want immutable job versions in Phase 4, or is snapshot-on-run sufficient for the first datastore-backed release?
4. Should tenant scoping remain user-based in every table, or should we introduce `workspace_id` as a nullable forward-compatibility column immediately?

## Recommended Next Step

Implement the domain classes and repository interfaces first, then add YAML repository implementations and a small loader that materializes the checked-in `Notion Place Inserter` YAML starter template for authenticated users without changing the execution semantics. In Phase 3, any edits should remain container-local and non-durable across Render restarts.
