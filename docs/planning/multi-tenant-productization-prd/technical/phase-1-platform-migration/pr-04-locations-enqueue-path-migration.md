# PR 04 - `/locations` Enqueue Path Migration

## Objective

Migrate `POST /locations` from in-memory enqueueing to durable Supabase queue enqueueing while preserving request/response contract.

## Scope

- Replace in-memory queue usage in route path with Supabase queue send.
- Persist initial job and run records at enqueue time.
- Keep response shape compatible:
  - `{ "status": "accepted", "job_id": "..." }` for async flow
- Preserve existing validation and error semantics where practical.

## Expected changes

- Updates in `app/routes/locations.py` and related queue usage paths.
- New persistence writes for enqueue lifecycle.
- Structured logging around enqueue success/failure with job identifiers.

## Acceptance criteria

- `/locations` returns accepted response and durable `job_id`.
- Enqueued request appears in Supabase queue and `platform_jobs`/`pipeline_runs`.
- Existing keyword validation behavior still passes tests.

## Out of scope

- Worker dequeue migration and run completion/failure persistence.

## Dependencies

- Requires PR 03.
