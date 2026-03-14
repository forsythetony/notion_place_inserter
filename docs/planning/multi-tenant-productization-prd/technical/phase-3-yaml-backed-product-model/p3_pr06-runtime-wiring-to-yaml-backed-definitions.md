# p3_pr06 - Runtime Wiring to YAML-Backed Definitions

## Objective

Migrate runtime execution from code-bound registries to YAML-backed definitions so jobs run from resolved snapshots instead of hard-coded pipelines.

## Scope

- Replace `app/app_global_pipelines/` and `app/custom_pipelines/` resolution with `JobDefinitionService` snapshot consumption
- Wire `JobExecutionService` (or equivalent) to accept a resolved snapshot and execute stages, pipelines, and steps in order
- Implement signal/binding resolution: `signal_ref`, `cache_key_ref`, `static_value`, `target_schema_ref`
- Map step templates to runtime step implementations (e.g., `step_template_optimize_input_claude` -> existing Optimize Input logic)
- Preserve run-scoped cache behavior; pipelines can read/write shared cache keys
- Ensure `places_service` (or trigger entry point) loads job from YAML/bootstrap and executes via snapshot

## Expected changes

- Refactor of `places_service` and pipeline orchestration to use snapshot-driven execution
- Step template ID to runtime implementation mapping
- Binding resolution logic for input_bindings
- Deprecation or removal of hard-coded `places_global_pipeline` and similar registries

## Acceptance criteria

- Triggering the location inserter flow loads the `Notion Place Inserter` job from YAML and executes from a snapshot
- Stages run sequentially; pipelines within a stage run in parallel; steps within a pipeline run sequentially
- Signal bindings resolve correctly (trigger.payload, step outputs, cache keys)
- Run-scoped cache is shared across pipelines in a run
- No execution path depends on code-bound pipeline registries

## Out of scope

- Run/usage record persistence (p3_pr08)

## Dependencies

- Requires p3_pr01 through p3_pr05.

---

## Manual validation steps (after implementation)

1. Trigger a job run (e.g., via existing `/locations` or equivalent) and confirm execution completes.
2. Verify stages and pipelines execute in correct order.
3. Inspect logs or debug output to confirm snapshot is used, not code registries.
4. Confirm run-scoped cache is populated and consumed across pipelines.

## Verification checklist

- [ ] Job runs from YAML-backed snapshot.
- [ ] Stage/pipeline/step order matches architecture.
- [ ] Signal bindings resolve correctly.
- [ ] Run-scoped cache works.
- [ ] Code-bound registries are no longer used for execution.
