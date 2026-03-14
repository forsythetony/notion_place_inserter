# p3_pr01 - Domain Entities and Ownership Model

## Objective

Establish the Phase 3 domain model foundation: pure data classes for the product hierarchy and ownership metadata so all later work uses stable, storage-agnostic types.

## Scope

- Define domain data classes for the canonical hierarchy: `Job -> Stage -> Pipeline -> PipelineStep`
- Add template vs instance separation: `ConnectorTemplate`/`ConnectorInstance`, `TargetTemplate`/`DataTarget`, `StepTemplate`/`StepInstance`
- Add schema and run entities: `TargetSchemaSnapshot`, `TargetSchemaProperty`, `TriggerDefinition`, `JobRun`, `StageRun`, `PipelineRun`, `StepRun`, `UsageRecord`
- Add `AppLimits` for abuse prevention
- Add ownership metadata to all persisted objects: `owner_user_id`, optional `workspace_id`, `visibility` (`platform` | `owner`)
- Ensure domain classes are pure data; no storage or orchestration logic

## Expected changes

- New domain module(s) with dataclasses or Pydantic models
- Field definitions matching the architecture doc (IDs, slugs, display names, config shapes, etc.)
- No repository or service implementations yet

## Acceptance criteria

- All domain classes from the architecture doc are defined with correct field types
- Ownership metadata is present on owner-scoped entities
- Template vs instance separation is explicit (e.g., `ConnectorTemplate` vs `ConnectorInstance`)
- Domain model is importable and usable without any YAML or Postgres dependencies

## Out of scope

- Repository interfaces or implementations
- Service layer
- YAML serialization/deserialization
- Execution or validation logic

## Dependencies

- None (first PR in sequence).

---

## Manual validation steps (after implementation)

1. Import all domain classes from the new module(s).
2. Instantiate representative objects (e.g., `JobDefinition`, `StepInstance`) with required fields.
3. Confirm ownership fields (`owner_user_id`, `visibility`) are present and typed correctly.
4. Run any existing tests to ensure no regressions from new imports.

## Verification checklist

- [x] All architecture-doc domain classes are defined.
- [x] Ownership metadata is on owner-scoped entities.
- [x] Template vs instance separation is explicit.
- [x] Domain module has no storage or orchestration dependencies.
