# PR 02 - Phase 1 Schema and Queue Foundation

## Objective

Introduce durable Phase 1 persistence tables and Supabase queue primitives required for async processing and run tracking.

## Scope

- Add migration(s) for Phase 1 tables:
  - `platform_jobs`
  - `pipeline_runs`
  - `pipeline_run_events`
  - `http_triggers` (minimal)
- Add indexes and uniqueness constraints for `job_id` and `run_id`.
- Enable and configure `pgmq` extension with queue name(s), for example `locations_jobs`.
- Add nullable forward-compatible columns (`owner_user_id`, `tenant_id`) where planned.

## Expected changes

- New SQL migration files under `supabase/migrations`.
- Optional seed/dev helper SQL for local testing.
- Short schema notes in docs for Phase 1 entities.

## Acceptance criteria

- Migrations apply cleanly on local Supabase.
- Queue exists and supports send/pop in manual smoke test.
- Table constraints prevent duplicate `job_id`/`run_id` inserts.

## Out of scope

- API route changes and worker logic changes.

## Dependencies

- Requires PR 01.
