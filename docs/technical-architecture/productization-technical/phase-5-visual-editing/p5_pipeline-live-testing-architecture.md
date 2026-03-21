# Architecture: Pipeline live testing from the editor

Date: 2026-03-20  
Status: Proposed  
Owner: Product + Platform

## Problem

The visual editor can create and save pipeline graphs, but it cannot execute them directly.

Today:

- users can manage triggers and define each trigger's `request_body_schema`
- jobs already link to exactly one trigger for editor purposes
- runtime execution already accepts `trigger_payload`, resolves a snapshot, and runs the full job

What is missing is the editor-facing layer that turns those pieces into a usable "live test" experience:

- there is no run button on the editor
- there is no **named, reusable test run setup** (akin to VS Code **Run and Debug** configurations)
- there is no first-class way to run **subgraphs** (job / stage / inner pipeline / single step) with explicit **fixture data** when upstream stages are skipped
- there is no clear contract for how a live test validates inputs, enqueues work, and reports scope

## Goals

1. Add **Test run configurations** (VS Code–style): named presets per job, created and edited in a dedicated modal, selectable from the editor toolbar (e.g. dropdown + **Run**).
2. Each configuration pins a **scope**: **job** | **stage** | **pipeline** (inner container) | **step**.
3. For every configuration, collect and persist **all inputs required for that scope**:
   - **Trigger body** (from the linked trigger's `request_body_schema`)
   - **fixtures** for dependencies **outside** the selected scope (e.g. cache keys normally populated by stage 1 when testing stage 2)
4. **Block saving** a configuration (or **Run**) until the dependency analyzer reports **no unsatisfied external bindings** — with inline guidance listing missing fixtures (not a silent runtime failure).
5. Reuse the existing snapshot-backed runtime and run persistence rather than a parallel "test-only" executor; apply scope by **filtering the snapshot** and optionally **pre-seeding the run cache / test resolution context** from fixtures.
6. **Propagate run status and errors to the editor via HTTP polling** against a management run-detail API (no WebSockets or SSE in v1).
7. **Orchestration boundary:** the worker/runtime must execute **only** the subgraph defined by the test run configuration — e.g. **stage 2 only must never run stage 3** (or any other out-of-scope stage, pipeline, or step).
8. **Destination write policy (editor live tests):** **mutating writes to the configured data target** (e.g. Notion page/property writes via terminal write steps) are **allowed only** when `scope_kind === job` for an editor-initiated test run. **Scoped** runs (`stage` | `pipeline` | `step`) are **non-mutating** with respect to the external destination.

## Non-goals (v1)

- Arbitrary **untyped** JSON blobs for every binding without validation or without tying fixtures to detected dependency keys (fixtures must be **traceable** to analyzer output).
- **Silent real writes** during scoped test runs — if a graph would persist to the destination, scoped configs must be **rejected at analysis** or **fail closed** at execution (see enforcement below).
- Editing trigger schema from the test configuration modal (trigger editing stays on Triggers / inspector).
- Real-time push updates (SSE/WebSockets) for run progress; **polling-only** progress and terminal status/errors in v1.
- Continuous stream logs inside the editor; linking to run history or a simple poll-driven summary is sufficient for v1.
- Automatically **inferring** realistic fixture values from production data or past runs (may be a later enhancement).

---

## Terminology

The product surface informally calls the top-level graph a "pipeline", but the backend model is:

- `JobDefinition` = top-level executable graph
- `StageDefinition` = outer container in the canvas
- `PipelineDefinition` = middle container inside a stage

To avoid confusion in the implementation:

- UI chrome may still say **Run** / **Run pipeline** for familiarity
- API/service contracts should name the top-level graph **job** and use explicit **`scope_kind`** values
- **Test run configuration** is the product term; it maps 1:1 to a persisted preset + scope + inputs/fixtures

**`scope_kind` (execution subgraph)**

| `scope_kind` | Binds to | Typical user mental model |
|--------------|----------|---------------------------|
| `job` | Whole `JobDefinition` | Run everything |
| `stage` | One `StageDefinition` | Run one outer container |
| `pipeline` | One inner `PipelineDefinition` | Run one horizontal pipeline branch |
| `step` | One `StepInstance` | Run from this step through the rest of its inner pipeline (or single-step only — see execution rules) |

Exact semantics for `step` scope (single step only vs run-to-end of inner pipeline) should be pinned in implementation and mirrored in the modal copy.

---

## Current anchors in the repo

| Area | Current anchor |
|------|----------------|
| Trigger input contract | `trigger_definitions.request_body_schema` and `app/services/trigger_request_body.py` |
| Job-trigger association | editor payload carries `trigger_id`; backend enforces one trigger per job in practice |
| Job persistence | `job_definitions.default_run_settings` already exists and is currently unused |
| Runtime execution | `JobExecutionService.execute_snapshot_run()` executes a resolved snapshot |
| Invocation pattern | `app/routes/locations.py` validates trigger input, resolves snapshot, and enqueues or runs |

These anchors make live testing mostly an orchestration and UX problem, not a new execution-engine problem.

---

## Proposed experience

### 1. Toolbar: pick a Test run configuration + Run

Mirror VS Code’s **Run and Debug**:

- **Dropdown:** lists saved **Test run configurations** for this job (e.g. "Full job — smoke", "Stage 2 — writeback with cache fixture").
- **Primary `Run`:** enqueues using the **selected** configuration (no modal if the config is complete and the graph is saved).
- **`Add configuration…` / gear:** opens the **Test run configuration** modal (create or edit).

Optional shortcuts:

- context menu on **stage / inner pipeline / step** → **Create test configuration from here…** (pre-fills `scope_kind` + target id).

### 2. Test run configuration modal (create / edit)

Single modal owns lifecycle + validation:

1. **Identity** — name, optional description.
2. **Scope** — `scope_kind` + target id (`stage_id` / `pipeline_id` / `step_id` as needed).
3. **Trigger input** — dynamic form from linked `request_body_schema` (required when a trigger is linked).
4. **Required fixtures** — populated by a **dependency analyzer** (server-side; client mirrors for UX):
   - lists every **external** requirement for the chosen subgraph: e.g. `cache_key_ref` reads that would be satisfied **outside** the scope, or `signal_ref` to steps **outside** the scope
   - for each row, the user supplies a value (JSON-safe), keyed the same way the analyzer reports (stable identity for save + diff)
   - **Save** and **Run** stay disabled until all rows are satisfied or the user narrows scope

**Example:** run **stage 2** only, but stage 1 normally performs a `cache_set` for `selected_place`. The analyzer flags a missing fixture for `cache_key_ref` like `{ "cache_key": "selected_place", "path": "some.field" }` (shape today: see `binding_resolver.py`). The user provides the structured value; only then can they save the configuration.

### 3. Quick run vs edit

- **Quick run:** toolbar uses last-selected config; if the graph or trigger schema changes, re-run analysis on load and surface a banner: **Configuration “X” needs updated fixtures** when stale.
- **Explicit edit:** opening the modal re-runs analysis against the **saved** graph revision (user must save pending editor changes first).

Recommended guardrails:

- if the graph has unsaved edits, block **Run** and ask the user to save first (runtime must match editor)
- if the trigger schema changed, mark affected configurations **stale** until the trigger section and any dependent fixture hints are re-validated

---

## Data model

### Recommendation: reuse `JobDefinition.default_run_settings`

Do not add a new top-level job column for v1. Store live-test settings inside the existing `default_run_settings` JSON field.

Suggested shape:

```json
{
  "live_test": {
    "schema_version": 2,
    "selected_config_id": "trc_01k8abcdef",
    "run_configurations": [
      {
        "id": "trc_01k8abcdef",
        "name": "Stage 2 — with cache fixture",
        "description": "Stage 1 skipped; seed selected_place",
        "scope_kind": "stage",
        "stage_id": "stage_writeback",
        "pipeline_id": null,
        "step_id": null,
        "trigger_input": {
          "keywords": "coffee shops",
          "limit": 10
        },
        "fixtures": {
          "cache_entries": [
            {
              "cache_key": "selected_place",
              "path": null,
              "value": { "displayName": "…", "formattedAddress": "…" }
            }
          ],
          "step_output_fixtures": []
        }
      }
    ]
  }
}
```

**Fixture keys**

- **`cache_entries`** — align with `cache_key_ref` resolution (`cache_key`, optional `path` under the stored blob, `value` JSON). Pre-seed the **run-scoped cache** before the first resolved step executes.
- **`step_output_fixtures`** — optional escape hatch for **cross-scope `signal_ref`** when a binding points at a step outside the subgraph; each entry names a **stable fixture id** from the analyzer (see below). Resolver behavior for editor runs should prefer real step outputs when present, then consult fixtures.

Reasons:

- no schema migration required for the initial feature (still `default_run_settings` jsonb)
- configurations are **versioned with the job graph** in the same PUT (simple mental model)
- multiple named configs fit the VS Code mental model without inventing a new top-level table (a dedicated table remains an option if configs grow large)

### Validation rules

- every configuration's `trigger_input` must validate against the linked trigger's current normalized schema
- **`fixtures` must satisfy `analyze_test_run_config(snapshot, config) -> AnalysisResult`** with `unsatisfied_requirements` empty (server is source of truth; client preview may warn early)
- `scope_kind` + ids must reference nodes that exist in the saved graph
- duplicate `id` or duplicate **display `name`** (product choice) should be rejected or auto-suffixed

### Future-proofing

Extend the same `live_test` envelope:

- `last_run_result` / `last_run_id`
- imported / shared configs
- `dry_run_default` per configuration
- optional **Postgres normalization** (`job_test_run_configs` table) if jsonb size or concurrent edit conflicts become an issue

---

## API surface

### 1. Extend editor payloads

Extend `GET /management/pipelines/{id}` and `PUT /management/pipelines/{id}` to expose a normalized live-test section.

Recommended response field:

```json
{
  "id": "job_123",
  "trigger_id": "trigger_abc123",
  "live_test": {
    "selected_config_id": "trc_01k8abcdef",
    "run_configurations": [],
    "trigger_schema": {
      "schema_version": 1,
      "fields": {
        "keywords": { "type": "string" }
      }
    },
    "analysis_preview": {
      "trc_01k8abcdef": {
        "ok": false,
        "unsatisfied_requirements": [
          {
            "requirement_id": "req_cache_selected_place",
            "kind": "cache_key_ref",
            "binding": { "cache_key": "selected_place", "path": "title" },
            "step_id": "step_map_fields",
            "input_key": "place_name"
          }
        ]
      }
    }
  }
}
```

Implementation notes:

- `trigger_schema` should be derived server-side from the linked trigger so the UI can render trigger inputs without an extra fetch
- persisted data still lives in `default_run_settings`; **`run_configurations`** round-trip on `PUT`
- `analysis_preview` is optional on `GET` for faster editor load; the modal should still call **`POST …/live-test/analyze`** (or analyze on save) for authoritative results

### 2. Add / extend endpoints

**Run (enqueue)** — editor-initiated execution:

`POST /management/pipelines/{id}/run`

Suggested request (preferred — uses saved config):

```json
{
  "test_run_configuration_id": "trc_01k8abcdef",
  "trigger_input_override": null,
  "fixtures_override": null
}
```

Optional **inline** run (debugger-style "temporary" without saving first) — same validation, not persisted:

```json
{
  "inline": {
    "scope_kind": "stage",
    "stage_id": "stage_writeback",
    "trigger_input": { "keywords": "coffee shops" },
    "fixtures": { "cache_entries": [], "step_output_fixtures": [] }
  }
}
```

Suggested response:

```json
{
  "status": "accepted",
  "run_id": "run_123",
  "job_id": "job_123",
  "test_run_configuration_id": "trc_01k8abcdef",
  "scope_kind": "stage",
  "scope": {
    "stage_id": "stage_writeback",
    "pipeline_id": null,
    "step_id": null
  }
}
```

**Analyze** — used by the Test run configuration modal:

`POST /management/pipelines/{id}/live-test/analyze`

Body: same shape as a single `run_configuration` (or `id` of saved config + optional edits). Response: `unsatisfied_requirements[]` + human-readable hints + stable **`requirement_id`** keys for form fields.

### 3. Recommended backend behavior

When `POST /management/pipelines/{id}/run` is called:

1. Load job + linked trigger + resolve **either** saved `test_run_configuration_id` **or** validate `inline` payload.
2. Normalize and validate `trigger_input` with the same helper used by trigger invocation.
3. Run **`analyze_test_run_config`**; if anything is unsatisfied → **422** with the same requirement rows the modal uses (no partial enqueue).
4. Resolve the canonical snapshot with `JobDefinitionService.resolve_for_run(...)`.
5. **Filter** snapshot to `scope_kind` subgraph (`job` → no filter). Persist or pass **only** this filtered snapshot to the worker (or a hash + ref); the worker must **not** re-merge the full job graph from the datastore for execution. See [Scope firewall](#scope-firewall-orchestration-must-stay-inside-the-configuration).
6. Build **`RunExecutionPolicy`** for the message: at minimum `allow_destination_writes: (scope_kind == job)` for `invocation_source === editor_live_test`; always `false` for `stage` | `pipeline` | `step`.
7. Attach **fixture payload** and **execution policy** to queue message / run metadata so the worker applies **cache pre-seed** (and optional **test-only binding overrides**) before execution.
8. Persist run metadata (including `test_run_configuration_id`, `scope_kind`, `allow_destination_writes`, analyzer hash) and enqueue.

**Decision:** editor live tests are **async by default**. After `POST …/run` returns `run_id`, the UI observes completion exclusively via **polling** `GET /management/runs/{run_id}` (see [UI feedback loop](#ui-feedback-loop-how-run-status-and-errors-reach-the-graph)).

Reasons:

- long-running jobs should not tie up the editor request
- it matches the current worker-backed architecture
- future run-history UI can treat live tests and trigger-fired runs uniformly

Synchronous execution can remain a developer-only or future debug option.

---

## Scope execution model

### `job`

- Use the resolved snapshot **unchanged** (subject to normal validation).
- `fixtures` are optional; typical configs omit them or use them only to override/cache-seed for debugging.

### `stage`

- **Filter** the snapshot so only the selected `stage_id` remains at the top level (same technique as earlier drafts).
- **Analyzer:** any binding inside that stage that references **outside** the stage becomes a **requirement** unless covered by `fixtures`.

### `pipeline` (inner container)

- Filter to the parent stage, then to the single `pipeline_id` (drop sibling inner pipelines in that stage for this run), or rebuild an equivalent subgraph — implementation must pick one strategy and document it for round-trip / display consistency.
- Requirements: bindings pointing **outside** that inner pipeline (including sibling pipelines in the same stage, other stages, or missing cache) need fixtures.

### `step`

- Narrow execution to an inner pipeline containing `step_id`:
  - **Option A (simpler):** run **only that step** (fail if later steps exist and something still expects their outputs — analyzer should flag those as missing unless fixtures supplied).
  - **Option B (common “run from here”):** run **from that step to the end** of its inner pipeline (analyzer includes dependencies on **earlier steps in the same inner pipeline** as in-scope; anything upstream outside is a requirement).

Product should pick A vs B and reflect it in the modal subtitle.

### External dependencies and fixtures (core idea)

When the subgraph excludes producers, bindings may still **consume** data those producers would have written.

The **dependency analyzer** walks all `input_bindings` / config `values` (and any other resolved binding surfaces) **inside the scope** and classifies references:

| Kind | Example | Fixture strategy |
|------|---------|------------------|
| `trigger.payload.*` | trigger body field | user fills **trigger_input** (not a fixture row) |
| `static_value` | literal | none |
| `target_schema_ref` | schema-driven | none (snapshot provides) |
| `cache_key_ref` | `{ "cache_key", "path?" }` | **cache fixture** row for that key (+ path) unless another **in-scope** step is a proven producer |
| `signal_ref` | `step.*` outside scope | **step output fixture** row OR expand scope / run full job |

**Save / Run gating:** configurations are **invalid** while `unsatisfied_requirements` is non-empty. This replaces the earlier "hard block all non-self-contained stage runs" approach with an explicit **data contract** the author fills in the modal.

### Worker / runtime: applying fixtures

Before step execution begins for an editor test run:

1. Initialize run-scoped cache from `fixtures.cache_entries` (respect key + nested `path` merge rules — define whether `path` replaces a sub-key or requires full object).
2. Register `fixtures.step_output_fixtures` in a **test-only resolver hook** consulted when `signal_ref` targets missing steps.

Production trigger runs never carry these fixture payloads.

### Scope firewall (orchestration must stay inside the configuration)

**Requirement:** for editor live tests, execution **must not** run stages, inner pipelines, or steps **outside** the configured scope. Example: a configuration with `scope_kind: stage` and `stage_id: stage_2` must **never** execute **stage 3** (or stage 1), even if a bug regresses filtering.

**How:**

1. **Authoritative subgraph** — `build_scoped_snapshot` produces the **only** `ResolvedJobSnapshot` / job graph dict the worker passes to `JobExecutionService.execute_snapshot_run`. No second lookup that re-expands to the full job for this run id.
2. **Single iterator** — stage loop runs over `snapshot.stages` (or equivalent) as filtered; with a correct filter, **stage 3 is not in the list**, so it cannot run.
3. **Defense in depth** — carry **`expected_scope_boundary`** on the execution context (e.g. allowed `stage_id`(s), `pipeline_id`(s), `step_id`(s)). Before starting a step, assert the step’s ids are **within** the boundary; otherwise **fail the run** with a clear invariant violation (prevents “filtered snapshot + stray queue payload” accidents).
4. **Ordering** — do not run “remaining stages” after the scoped stage completes; terminal success is when the **scoped** subgraph finishes.

### Destination writes (editor live tests)

**Policy (explicit):** for `invocation_source === editor_live_test`, **mutating writes to the job’s data target** (e.g. Notion **Property Set** / page create / upload handlers that persist user-visible data) are **allowed only** when `scope_kind === job` **and** `allow_destination_writes === true`. **Scoped** configurations (`stage` | `pipeline` | `step`) set `allow_destination_writes === false`.

**Scope note:** production runs triggered via HTTP (`invocation_source` ≠ editor live test) keep **today’s** full-job semantics; this rule is specific to **editor test executions** so authors can safely dry-run subgraphs.

**Enforcement (defense in depth):**

1. **Analyzer (authoring):** when `scope_kind !== job`, treat in-scope steps whose templates are **destination-write** (maintain a registry: `property_set`, Notion create/upload, etc.) as **invalid** — **`422` on Save/Analyze** with copy like *“Writing to the database requires a full job test configuration.”* This prevents authors from expecting a scoped run to persist.
2. **Runtime (handlers):** every handler that performs an external **mutating** call must check `RunExecutionPolicy.allow_destination_writes` (or equivalent). If `false`, **do not call the provider**; return a structured error or mark the step `failed` with **`error_summary`** explaining scoped tests are read-only for destination writes — so a missed analyzer case still **cannot** mutate the destination.

**Non-mutation side effects:** scoped runs may still call **read-only** or **non-target** APIs (e.g. Google Places lookup) unless product later adds stricter “sandbox” flags — document separately if needed.

---

## Backend service design

Add a focused orchestration layer, for example `PipelineLiveTestService`, instead of placing all logic directly in the route.

Responsibilities:

- load job, trigger links, trigger schema, and saved **test run configurations**
- validate **trigger_input** and **fixtures** for a configuration (saved or inline)
- **`analyze_test_run_config`** — compute `unsatisfied_requirements` with stable ids for modal form binding
- **`build_scoped_snapshot`** — filter snapshot to `scope_kind` + target ids
- attach **fixture instructions** and **`RunExecutionPolicy`** (`allow_destination_writes`, scope boundary) to the queue payload / run row metadata
- enqueue the run with metadata

Suggested helpers:

- `get_live_test_context(job_id, owner_user_id) -> LiveTestContext`
- `validate_trigger_input(trigger, payload) -> dict[str, Any]`
- `analyze_test_run_config(snapshot, config) -> TestRunAnalysis` (includes **destination-write** validation for scoped configs)
- `build_scoped_snapshot(snapshot, scope_kind, scope_ids) -> ResolvedJobSnapshot`
- `assert_step_within_scope(policy, step_ids) -> None` (fail fast if invariant violated)
- `merge_fixtures_into_run_context(ctx, fixtures) -> None` (worker-side)
- `enqueue_live_test(...) -> LiveTestAcceptedResponse`

This keeps the editor-specific control plane separate from public trigger invocation while still reusing the same runtime primitives.

The **analyzer** should share as much logic as possible with existing binding / validation code paths so editor analysis matches worker resolution (avoid duplicating `binding_resolver` rules in the frontend beyond trivial previews).

---

## Run metadata and observability

Live tests should be easy to distinguish from trigger-fired runs.

Recommended run metadata additions:

```json
{
  "invocation_source": "editor_live_test",
  "test_run_configuration_id": "trc_01k8abcdef",
  "test_run_configuration_name": "Stage 2 — with cache fixture",
  "scope_kind": "stage",
  "scope": {
    "stage_id": "stage_writeback",
    "pipeline_id": null,
    "step_id": null
  },
  "allow_destination_writes": false,
  "trigger_id": "trigger_abc123",
  "analyzer_requirements_hash": "sha256:…"
}
```

Use cases:

- filtering run history
- debugging "why did only this stage execute?"
- correlating failures with the exact fixture set the author saved
- proving whether a run was **eligible** to mutate the destination (`allow_destination_writes`)
- future analytics on editor usage vs production trigger usage

**As implemented (v1):** editor runs also set `trigger_payload._live_test_meta` (analyzer hash, scope, `allow_destination_writes`, optional `test_run_configuration_id`) and attach a top-level **`live_test`** object on the **queue message** (scope, fixtures, `api_overrides`). No `job_runs.metadata` JSON column was required.

### External API call sites vs `allow_destination_writes`

| Control | Governs | Examples |
|--------|---------|----------|
| **`allow_destination_writes`** | **Destination persistence** to the configured Notion data target | Final `create_page`, `property_set` schema writes, Notion image upload when not external-only |
| **`api_overrides`** (`call_site_id` → `{ enabled, manual_response }`) | **Optional outbound integrations** (network/SDK), including reads | Claude (optimize / prompt / constrain / relation), Google Places, Freepik, Notion upload slot |

If a call site is **disabled**, runtime returns **`manual_response`** without I/O and logs `external_api_skipped`. Analysis **`422`**s if disabled without `manual_response`. Handlers wired include optimize input, Google Places, AI prompt/constrain/relation, search icons, upload image (Notion slot).

---

## UI feedback loop: how run status and errors reach the graph

Async `POST /management/pipelines/{id}/run` only proves the run was **accepted**. Everything after that (worker execution, step failures, external API errors) must flow through **durable run records** that the UI reads.

### Two classes of errors

| When | Where it surfaces | UX |
|------|-------------------|-----|
| **Before enqueue** | HTTP response from `POST …/run` | Inline in the modal or toolbar: validation failures (bad trigger body, no trigger link, **unsatisfied fixture requirements**, job disabled, etc.). Same pattern as trigger `400/422`. |
| **After enqueue** | Run + step rows in Postgres (and optional event rows) | Not available on the POST response. UI **polls** `GET /management/runs/{run_id}` (and step/tree detail as needed) until terminal status. |

### Decision: poll a run detail API (v1)

Implementation must ship owner-scoped read APIs (names illustrative):

- **`GET /management/runs/{run_id}`** — job run header: `status`, `error_summary`, `started_at` / `completed_at`, `job_id`, `invocation_source`, `scope`, `scope_id`, plus nested summary or ids for child runs.
- **`GET /management/runs/{run_id}/steps`** (or embed in the same payload) — flat or tree of `stage_run` → `pipeline_run` → `step_run` with `step_id`, `status`, `error_summary`, timestamps.

The domain model already carries run-level and step-level summaries (`JobRun.error_summary`, `StepRun.error_summary` in `app/domain/runs.py`). The contract for the UI should treat **`error_summary` as the primary human-readable failure line** for toasts and inspector copy; optionally extend later with structured `error_detail` JSON for field-level rendering.

**Polling strategy (editor) — required behavior:**

- After `POST …/run` returns `run_id`, start polling `GET /management/runs/{run_id}` on a backoff schedule (e.g. 500ms → 1s → 2s, cap ~5s) until `status` is terminal (`succeeded`, `failed`, `cancelled` — align with existing enums).
- Use **one in-flight request at a time** per `run_id` (no overlapping polls); cancel or skip if the component unmounts or the user navigates away.
- Stop polling on terminal state; clear `activeRunId` when the user dismisses the run UI or starts a new run (product choice: allow concurrent run banners vs single active run).
- While status is `queued` / `running`, refresh the graph highlight from the latest payload only when **step-level** `status` is present in the response (cheap progress UX); otherwise show a non-blocking **Run in progress…** banner with optional **Open run details**.
- Do not add SSE/WebSocket clients for run status in v1; if live step-by-step updates are needed later, they are a **separate phase** and may still keep polling as fallback.

**Optional v1 enhancement (still polling):** append-only **`pipeline_run_events`** exposed as `GET /management/runs/{run_id}/events?after_seq=` — the UI **polls** this endpoint for a richer timeline; it does not switch the transport to push.

### Mapping failures back onto the graph

Graph nodes already reference definition ids (`stage_id`, inner `pipeline_id`, `step_id` on step instances). Step run rows should use the **same `step_id`** as the graph step node.

Recommended mapping:

- **`step_run.status === failed` and `error_summary` set** → highlight that **step node** (border + badge), and optionally scroll/focus it.
- **`stage_run` / `pipeline_run` failed** without a single failing step (orchestration error) → highlight the **stage** (or inner pipeline) header and show `JobRun.error_summary` in a run panel.
- **Multiple failed steps** (if parallel pipelines within a stage) → highlight all failed step nodes; primary message = first failure by timestamp or lexicographic `step_id` (product choice).

This gives users a direct link between **observed runtime failure** and **the node they see on the canvas**, consistent with a **polling-only** v1.

### Where to show errors in the UI

| Surface | Content |
|---------|---------|
| **Run modal / drawer** | Last poll snapshot: terminal status, top-level `error_summary`, **failed step name + id** with jump-to-node. |
| **Toast** | Short message on terminal failure; success variant when `succeeded`. |
| **Persistent run strip (optional)** | Thin bar under the editor toolbar while `running`; expands to show failure detail on complete. |
| **Future: Run history page** | Full list + detail; same APIs. |

### Deferred: push updates (not v1)

SSE or WebSocket keyed by `run_id` is **out of scope** for live testing v1. **Polling is the sole mechanism** for run status and errors. Revisit push only if product requires sub-second step updates at scale; keep polling as a fallback for reliability.

---

## Frontend architecture (`notion_pipeliner_ui`)

### Editor state

Add a `liveTest` slice or equivalent derived editor state:

- `triggerSchema` (from `GET` projection)
- `runConfigurations[]` + `selectedConfigurationId`
- `configurationDraft` (modal local state)
- `analysisResult` / `unsatisfiedRequirements` (from analyze endpoint)
- `triggerInput` (per configuration)
- `fixtures` (per configuration; keyed by `requirement_id` or structured rows)
- `isRunning`
- `activeRunId` (from `POST …/run`)
- `activeRunStatus` / `activeRunError` (from polling `GET /management/runs/{run_id}`)
- `failedStepIds` / `failedStageIds` (derived from run detail for graph highlighting)

### Components

Suggested pieces:

| Component | Responsibility |
|----------|----------------|
| `TestRunConfigurationDropdown` | VS Code–style config picker in editor chrome |
| `TestRunPrimaryButton` | Starts run for selected configuration |
| `TestRunConfigurationModal` | Create/edit configs: scope, trigger input, fixture rows |
| `TestRunFixturesPanel` | Renders analyzer requirements + value editors (JSON textarea with validation for v1) |
| `TestRunAnalyzeButton` | Triggers `POST …/live-test/analyze` (also auto on blur / scope change) |
| `useRunPoll` (hook) | Backoff polling of `GET /management/runs/{run_id}` until terminal; exposes status + errors |
| `RunFeedbackBanner` | Toolbar strip: in-progress / failed; shows **configuration name** |

### UX details

- Saving the job graph persists configurations; **Run** requires a saved graph.
- **Run** without opening the modal is allowed only when the selected configuration passes analysis.
- Offer **inline run** (temporary) only for power users if product wants it; same analyzer gates apply before enqueue.
- After acceptance, show a toast: **Running "Configuration name"…** with `View run`.
- When polling observes **terminal failure**, show summary with **which configuration** ran and **`error_summary`**; offer **jump to failed node** when `step_id` is present.

---

## Failure modes

| Failure | Recommended behavior |
|--------|----------------------|
| No linked trigger | Disable run UI and show "Link a trigger to test this pipeline" |
| Trigger schema changed | Mark configs **stale**; block run until trigger inputs re-validated in the modal |
| Analyzer finds missing fixtures | Block **Save** on the configuration and block **Run** until requirements satisfied (show rows with jump-to-binding in graph) |
| Scoped config includes destination-write steps | **422** on analyze/save: require **full job** scope (or remove write steps from subgraph) |
| Handler invoked despite `allow_destination_writes: false` | Fail step/run with explicit error — must not call external mutating APIs |
| Step id outside scoped snapshot (invariant bug) | Fail run immediately — **scope firewall** violation |
| Fixture value JSON invalid | Inline field errors in the modal |
| Job has unsaved changes | Ask user to save first so runtime matches the visible graph |
| Queue or run persistence unavailable | Return normal API error; do not silently fall back to sync execution |
| Run accepted but worker fails later | Poll surfaces terminal `failed` + `error_summary`; map `step_id` to graph node when present |
| Poll never reaches terminal (worker stuck / lost message) | After N minutes or max polls, show "Run status unknown" with link to run history / support |

### Local dev: API logs `management_live_test_enqueued` but the worker stays quiet

Editor runs **enqueue** only (`pgmq_send`); **pipeline execution logs appear in the worker process**, not uvicorn. If the worker prints `worker_starting` and then only `worker_queue_poll_idle`, **pgmq has no visible messages** for this worker — either nothing was enqueued into **this** database, or a message was already consumed.

Checklist:

1. **Confirm the UI talks to the API you think** — In `notion_pipeliner_ui/.env`, `VITE_BASE_URL` must be **`http://localhost:8000`** (or whatever host runs `make run`). If it points at **Render/production**, enqueue goes to **that** deployment’s Supabase; your **local** worker (polling `127.0.0.1:54321`) will stay idle forever. Restart `npm run dev` after changing `.env`.
2. **API line on Run** — After a successful Run, uvicorn should log  
   `management_live_test_enqueued | ... pgmq_message_id=<n> queue_name=locations_jobs`.  
   **No such line** ⇒ the POST did not hit this API or returned 4xx before enqueue (check browser Network tab: request URL host).
3. **Worker** — Run `make run-worker` in a **separate terminal** before clicking Run; startup includes `queue_name=<name>` and `supabase_host=<host>` — must match API (`SUPABASE_URL` / `SUPABASE_SECRET_KEY`).
4. **`SUPABASE_QUEUE_NAME`** — Unset ⇒ both default to `locations_jobs`. Set it on **both** API and worker if you override.
5. **Idle** — With `LOG_LEVEL=DEBUG`, the worker emits `worker_queue_poll_idle` every ~30s when empty.
6. **Dequeue** — When a message is read, look for `worker_dequeued | queue_name=... run_id=...`.

---

## Rollout plan

### Phase A: configurations + job scope

- Test run configuration modal (name, `scope_kind=job`, trigger inputs only)
- toolbar picker + Run + polling feedback
- `POST …/run` + `GET …/runs/{id}`

### Phase B: subgraph scopes + analyzer

- add `stage` / `pipeline` / `step` scopes + snapshot filtering
- enforce **scope firewall** (filtered snapshot only; per-step boundary assert; no “continue to stage 3” after stage 2)
- ship **`RunExecutionPolicy`** with `allow_destination_writes: false` for scoped runs; **analyze-time block** for destination-write steps outside full job
- ship **`POST …/live-test/analyze`** and **fixture-gated saves**
- worker: **cache pre-seed** from `fixtures.cache_entries`

### Phase C: cross-scope `signal_ref` fixtures

- `step_output_fixtures` + test-only resolver hook
- richer requirement UX (jump-to-node, suggested JSON templates per step template)

Phases B–C are where VS Code–style "launch.json for pipelines" pays off; Phase A can land without fixtures.

---

## Testing matrix

| Area | Cases |
|------|-------|
| API | run by `test_run_configuration_id`; inline run; analyze returns requirements; 422 when fixtures incomplete |
| Persistence | `run_configurations[]` round-trips; `selected_config_id` restored in editor |
| Analyzer | stage-2-only config flags upstream `cache_key_ref`; satisfied after fixture save |
| Worker | scoped snapshot executes **only** in-scope stages/steps; later stages never run; `allow_destination_writes` honored by write handlers |
| Scope firewall | integration: stage_2-only run does not create stage_3 `stage_run` / step rows |
| Destination writes | scoped run with property_set **blocked at analyze**; if bypassed, handler does not mutate |
| UI | modal blocks save until requirements empty; toolbar run disabled when stale |
| Run detail + polling | `GET /management/runs/{id}` includes metadata tying back to configuration id/name |
| Graph highlight | failed `step_id` matches graph; optional highlight of binding source for stale configs |

---

## Open questions

1. **`step` scope:** single-step only vs run-to-end of inner pipeline (Option A vs B above)?
2. **Cache fixture merge:** when `path` is set, deep-merge vs replace — must match worker semantics exactly.
3. Should we allow **import/export** of test run configurations as JSON (team sharing), or keep them job-embedded only for v1?
4. Should **`signal_ref` fixtures** be v1 if most scoped runs only need cache keys, or defer to Phase C?
5. Do we want a per-configuration **`dry_run`** flag, or a global operator toggle?
