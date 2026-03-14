# p3_pr05 - Job Definition Resolution and Snapshotting

## Objective

Implement job-definition resolution and snapshotting so runs execute against a resolved definition snapshot, not a moving target.

## Scope

- Add `JobDefinitionService` (or equivalent) that resolves a job by ID into a complete snapshot
- Snapshot includes: job definition, referenced stage/pipeline/step definitions, trigger definition, target definition, active target schema snapshot
- Snapshot is immutable and suitable for persistence (YAML in Phase 3, JSONB in Phase 4)
- Add `definition_snapshot_ref` (or equivalent) to `JobRun` so runs are tied to the snapshot they executed against
- Ensure resolution follows owner boundaries; one user cannot resolve another user's definitions

## Expected changes

- `JobDefinitionService` with `resolve_for_run(job_id, owner_user_id)` returning a snapshot
- Snapshot data structure (e.g., nested dict or domain object) containing all referenced entities
- Integration point for execution layer to consume snapshots

## Acceptance criteria

- Resolved snapshot contains job, stages, pipelines, steps, trigger, target, and active schema
- Snapshot is complete and self-contained for execution
- Resolution is owner-scoped; cross-tenant resolution is rejected
- Snapshot can be persisted (e.g., as YAML or JSON) for debugging and replayability

## Out of scope

- Actual execution logic (p3_pr06)
- Run persistence (p3_pr08)
- Trigger/target/schema repository implementations (p3_pr07)

## Dependencies

- Requires p3_pr01, p3_pr02, p3_pr03, p3_pr04, p3_pr07 (trigger/target/schema repos for resolution).

---

## Manual validation steps (after implementation)

1. Resolve the bootstrap `Notion Place Inserter` job for an authenticated user; confirm snapshot contains all stages, pipelines, steps, and referenced entities.
2. Attempt to resolve a job for a different owner; confirm rejection or empty result.
3. Persist a snapshot to YAML/JSON and confirm it is self-contained and parseable.

## Verification checklist

- [ ] Snapshot contains job, stages, pipelines, steps, trigger, target, schema.
- [ ] Resolution is owner-scoped.
- [ ] Snapshot is immutable and persistable.
- [ ] Execution integration point is clear.
