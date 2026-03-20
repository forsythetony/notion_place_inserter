# p5_pr04 - Visual Pipeline Editor with Graph Persistence via API

## Objective

Deliver the pipeline editor experience where selecting an existing pipeline or creating a new one opens a graph canvas that can be edited and persisted. Use React Flow for the graph UI; transform between backend structured definitions and graph state; persist changes through Phase 4 APIs.

## Scope

- Implement React Flow-based editor route with:
  - graph load from persisted definition (backend → graph state)
  - create/add/remove/reorder graph elements aligned to `Job -> Stage -> Pipeline -> PipelineStep`
  - canvas lock/read-only mode during save and guarded operations
- Add transformation layer:
  - backend structured definition → graph state (nodes, edges, viewport)
  - graph state → backend save payload
- Persist changes through API and refresh local graph from canonical saved response
- Enforce save-time guardrails surfaced in UI: terminal-step rule, validation failures from backend
- Apply p5_pr01 pipeline-editor styling (nodes, edges, selection, hover, connect states)

## Expected changes

- Editor route (e.g. `/pipelines/:id` and `/pipelines/new`)
- React Flow canvas with custom node types for Stage, Pipeline, PipelineStep
- Serialization/deserialization between graph state and backend job definition format
- API integration: GET job definition, PUT/PATCH job definition, validation endpoint
- Save button with loading/locked state; validation error display
- Integration with p5_pr03 Pipelines list (open/create handoff)

## Acceptance criteria

- User can open existing pipeline and see consistent graph reconstruction from persisted definition
- User can create new pipeline graph, save, reload, and get stable round-trip fidelity
- Validation errors (terminal-step rule, ID resolution, etc.) are actionable in editor UI and block invalid saves
- Editor integrates with dashboard list flow (Pipelines page handoff from p5_pr03)
- Canvas supports lock/read-only during save
- Styling matches p5_pr01 pipeline-editor.md (nodes, edges, selection, connectors)

## Out of scope

- Structured text view or dual-view switching (future enhancement; PRD allows it but not required for Phase 5 completion)
- Pipeline versioning or draft/published workflow states
- Real-time collaboration or conflict resolution
- Step configuration panels (basic step add/remove/reorder only; rich config UI can be follow-up)

## Dependencies

- p5_pr01 design rules for editor visuals and interactions
- p5_pr03 pipelines list route and create/open handoff
- Phase 4 APIs for job definition persistence and validation

---

## Manual validation steps (after implementation)

1. From Pipelines list, click "Create New"; confirm editor opens with empty or template graph.
2. Add stages, pipelines, steps; save; confirm API success.
3. Reload page or navigate away and back; confirm graph reconstructs correctly.
4. Open existing pipeline; confirm graph loads from definition.
5. Make invalid change (e.g. remove terminal Property Set); attempt save; confirm validation blocks and shows error.
6. Verify canvas locks during save (no drag/connect while saving).

## Verification checklist

- [ ] Editor route accessible from Pipelines list create/open
- [ ] Graph loads from backend definition
- [ ] Graph saves to backend with round-trip fidelity
- [ ] Validation errors displayed and block invalid save
- [ ] Canvas lock during save
- [ ] React Flow used per [pipeline-editor-library-research.md](../../../market-research/pipeline-editor-library-research.md)
- [ ] Styling matches p5_pr01 pipeline-editor.md
