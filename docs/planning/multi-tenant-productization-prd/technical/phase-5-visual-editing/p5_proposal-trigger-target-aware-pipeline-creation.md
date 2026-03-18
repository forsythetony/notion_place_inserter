# Proposal: Trigger + Target Aware Pipeline Creation and Target Schema Inspector

Date: 2026-03-16  
Status: Proposed  
Owner: Product + Platform

## Why this proposal

The current create-pipeline flow creates a draft graph with a default target fallback and no explicit trigger selection. This can create ambiguity at authoring time (what starts this pipeline, and where does it end), and it does not expose target schema details in the graph inspector where users configure mapping logic.

This proposal introduces:

1. A guided creation flow that requires choosing both a trigger and a target.
2. A trigger node at the top and a target-aware terminal node at the bottom of every initial draft graph.
3. A details-pane experience that shows destination schema details (property name, type, and selectable options for select-like fields).

## Goals

- Ensure every newly created pipeline has explicit trigger and target associations from the first save.
- Make both pipeline boundaries visible in the graph: trigger at start, target at end.
- Let users inspect target schema details without leaving the pipeline editor.
- Preserve compatibility with existing Notion-backed pipelines.

## Non-goals

- Full trigger builder redesign (this proposal uses existing trigger entities).
- Full target onboarding redesign (this proposal uses existing target/data-source entities).
- Multi-destination pipeline support in this phase.

## User experience changes

## 1) New "Create Pipeline" guided modal

When the user clicks "Add Pipeline" (or navigates to `/pipelines/new`), show a modal instead of creating immediately.

Modal fields:

- `Pipeline name` (optional; defaults to "New Pipeline")
- `Trigger` (required dropdown)
  - Source: `GET /management/triggers`
  - Show display name + path for clarity
- `Target` (required dropdown)
  - Source: `GET /management/data-targets` (or equivalent owner-scoped target list endpoint)
  - Show display name + connector badge (Notion) + schema freshness indicator

Actions:

- `Create pipeline` (enabled only when trigger + target selected)
- `Cancel`

Failure/empty states:

- No triggers available -> CTA: "Create Trigger"
- No targets available -> CTA: "Connect Notion Database"

## 2) Initial graph now includes explicit start and end nodes

Every created pipeline should include:

- a top-level "Trigger" node at the very top of the graph, representing how execution starts.
- a final "Target" node at the very bottom of each pipeline branch, representing where output lands.

For current scope (Notion page destination), the target node references the selected target's active schema snapshot.

Behavior:

- Trigger and target nodes are auto-created during pipeline bootstrap.
- Trigger node is visually first; target node is visually terminal (no outgoing edges).
- Trigger node displays selected trigger metadata (`trigger_id`, display name, path, method) and supports quick navigation to trigger details.
- Target node is read-only for structural fields (`target_id`, schema reference), but can expose mapping helpers.
- Existing `property_set` steps continue to exist for write behavior; trigger/target nodes act as start/end context surfaces.

## 3) Target node inspector: schema details in the right pane

When the user selects the target node in the graph:

- Show target summary:
  - Target display name
  - Connector type (`notion`)
  - External source/database name and id
  - Last schema sync timestamp
- Show property catalog table:
  - Property display name
  - Property type (title, rich_text, number, select, multi_select, relation, date, url, etc.)
  - Internal property id (for advanced mapping/debug)
  - Allowed values for `select`/`multi_select`
  - Additional type metadata where available (number format, relation target, etc.)

Quality-of-life:

- Search/filter by property name
- Type chips for fast scanning
- Empty-state messaging for stale/missing schema with "Refresh schema" CTA

## 4) Trigger node inspector: trigger details in the right pane

When the user selects the trigger node in the graph:

- Show trigger summary:
  - Trigger display name
  - Path and method
  - Trigger type/auth mode
  - Last updated timestamp
- Show linked job context:
  - This pipeline's job id
  - Link status (linked/unlinked for legacy)
- Provide quick actions:
  - "Go to Triggers"
  - "Rotate secret" (optional shortcut if in scope)

## Data and model updates

## Editor graph model

Add new node types in the editor transform layer:

- `trigger` and `target` node types (siblings to existing `stage`, `pipeline`, `step` render types)
- Exactly one top-level trigger node per graph, bound to selected `trigger_id`
- Each pipeline branch can end with one `target` node that binds to `job.target_id`
- Graph transform (`graphToFlow`/`flowToGraph`) must preserve both nodes deterministically

Important: This is primarily a UI/editor representation. Runtime execution still uses validated job graph semantics and existing terminal step constraints.

## Backend create pipeline contract

Current behavior allows minimal body and derives target fallback. Proposed creation contract:

- Request:
  - `display_name?: string`
  - `trigger_id: string` (required)
  - `target_id: string` (required)
- Response:
  - Full editable payload with trigger + target references included (for top trigger node and bottom target node projection)

Validation:

- `trigger_id` must belong to authenticated owner
- `target_id` must belong to authenticated owner
- Return 422 with actionable codes (`NO_TRIGGER`, `NO_TARGET`, `INVALID_TRIGGER`, `INVALID_TARGET`)

Linking:

- On creation, attach selected trigger to created job via existing trigger-job linking mechanism.
- Keep many-to-many compatibility for future multi-job trigger fanout.

## Target schema read API

Add (or reuse) owner-scoped endpoint to hydrate inspector with full schema detail:

- `GET /management/data-targets/{target_id}/schema`
- Returns active schema snapshot plus enriched property metadata:
  - `property_id`
  - `name`
  - `type`
  - `select_options[]` / `multi_select_options[]` when applicable
  - `metadata` map for type-specific details
  - `last_synced_at`

Caching:

- Cache by `target_id` + schema snapshot id during editor session.
- Manual refresh invalidates cache and re-fetches.

## Implementation plan

1. **API prep**
   - Extend create-pipeline request/validation for required `trigger_id` + `target_id`.
   - Ensure trigger-job association is created at pipeline creation.
   - Expose schema metadata endpoint for target inspector.

2. **Create modal UI**
   - Add modal state and fetch triggers/targets before submission.
   - Disable creation until required selections are present.
   - Route `/pipelines/new` into modal-first flow.

3. **Graph changes**
   - Introduce `trigger` and `target` node renderers and deterministic layout placement.
   - Place trigger node at top anchor, stage/pipeline/step graph in middle, and target nodes as branch terminals at bottom.
   - Update graph transform tests for round-trip consistency with trigger/target nodes.

4. **Inspector changes**
   - Add `TriggerInspector` panel branch.
   - Add `TargetInspector` panel branch.
   - Render searchable property table with type and options.
   - Add refresh action + stale schema messaging.

5. **Migration/compatibility**
   - Existing pipelines without explicit trigger association should still load.
   - Editor can show "Unlinked trigger" banner for legacy records and offer linking action.

## Acceptance criteria

- Creating a pipeline requires selecting both trigger and target.
- New pipeline persists with valid trigger-job link and job target id.
- New graph renders with an explicit trigger node at the top and terminal target node at the bottom.
- Clicking trigger node shows trigger metadata and link status.
- Clicking target node shows property name/type and selectable options for select-like fields.
- Save/load round trips preserve graph shape and data references.
- Legacy pipelines remain editable.

## Risks and mitigations

- **Schema staleness:** Notion schema may drift after creation.  
  Mitigation: timestamped schema display + manual refresh control in inspector.

- **UI complexity increase at creation:** modal adds one step.  
  Mitigation: smart defaults (preselect most recently used trigger/target), keyboard-first flow.

- **Runtime/editor model mismatch:** trigger/target nodes are representational.  
  Mitigation: keep runtime validation based on canonical job graph; start/end nodes stay projection-only in transform layer.

## Open questions

- Should creation allow "Save as draft" when trigger is missing, or enforce strict required trigger from day one?
- Should each pipeline branch support a unique target in future, or keep job-level `target_id` only?
- Do we want inline schema option pickers directly inside step forms (`property_set`) in this same effort, or as a follow-up ticket?

