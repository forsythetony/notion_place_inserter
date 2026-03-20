# p3_pr04 - Definition Validation Service

**Status:** Complete (2026-03-14)

## Objective

Implement a `ValidationService` that enforces definition integrity at save time: ID resolution, sequencing, limits, and the Property Set terminal rule.

## Scope

- Add `ValidationService` with validation methods for jobs, stages, pipelines, step instances, triggers, and targets
- Enforce: referenced IDs exist and belong to same owner (unless platform-owned)
- Enforce: job has at least one stage; stage has at least one pipeline; pipeline has at least one step
- Enforce: stage sequences unique within job; pipeline sequences unique within stage; step sequences unique within pipeline
- Enforce: trigger paths unique per owner (path is the segment used in `/triggers/{owner_user_id}/{path}`)
- Enforce: Property Set is the final step of any property-setting pipeline; Property Set references a real target schema property on the job's target
- Enforce: step input bindings resolve to known signal/cache/schema sources
- Enforce: object counts do not exceed `AppLimits` (max_stages_per_job, max_pipelines_per_stage, max_steps_per_pipeline)
- Integrate validation into save paths (repository or service layer) so invalid definitions are rejected before persistence

## Expected changes

- New `ValidationService` module
- Validation rules implemented per architecture doc
- Integration with job/target/trigger save flows

## Acceptance criteria

- Invalid definitions (missing IDs, bad sequences, violated limits, non-terminal Property Set) are rejected with clear errors
- Valid definitions pass validation
- Validation runs on save, not only at execution time

## Out of scope

- Execution-time defensive checks (separate concern; can be added in p3_pr06)
- UI validation feedback (future phase)

## Dependencies

- Requires p3_pr01 (domain entities), p3_pr02 (repository interfaces), p3_pr03 (YAML catalog and bootstrap).

---

## Manual validation steps (after implementation)

1. Attempt to save a job with a missing stage; confirm rejection.
2. Attempt to save a pipeline with Property Set not as final step; confirm rejection.
3. Attempt to save a job exceeding stage limit; confirm rejection.
4. Save a valid `Notion Place Inserter`-like job and confirm success.

## Verification checklist

- [x] Referenced ID resolution is enforced.
- [x] Sequencing rules are enforced.
- [x] Property Set terminal rule is enforced.
- [x] Limits are enforced.
- [x] Valid definitions pass.
