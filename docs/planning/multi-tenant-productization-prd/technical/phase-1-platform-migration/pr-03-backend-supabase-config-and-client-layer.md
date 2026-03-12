# PR 03 - Backend Supabase Config and Client Layer

## Objective

Add backend infrastructure code needed to talk to Supabase safely from FastAPI and worker processes, without changing request behavior yet.

## Scope

- Add Supabase-related environment configuration:
  - project URL
  - service credential/key for trusted backend contexts
  - queue/table names
- Create a small service/repository layer for:
  - queue operations (send/pop/ack abstraction)
  - job/run/event persistence operations
- Add startup validation for required Supabase env vars (similar to existing required provider keys).

## Expected changes

- New backend modules under `app/services/` or `app/integrations/` for Supabase interaction.
- Config constants and typed helpers for environment parsing.
- No route contract changes yet.

## Acceptance criteria

- App starts with clear errors when Supabase env vars are missing/malformed.
- Supabase adapter functions can be called from unit tests with mocks/fakes.
- Existing non-Supabase behavior remains unchanged.

## Out of scope

- Switching `/locations` enqueue path or worker consumer path.

## Dependencies

- Requires PR 02.
