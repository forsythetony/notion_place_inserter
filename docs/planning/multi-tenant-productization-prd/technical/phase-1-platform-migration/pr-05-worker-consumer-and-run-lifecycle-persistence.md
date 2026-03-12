# PR 05 - Worker Consumer and Run Lifecycle Persistence

## Objective

Move background execution to a Supabase-backed consumer flow and persist full run lifecycle transitions (start/success/failure).

## Scope

- Replace in-memory worker dequeue source with Supabase queue pop/read.
- Execute existing pipeline logic unchanged (`PlacesService.create_place_from_query`).
- Persist state transitions:
  - queued -> running -> succeeded/failed
- Persist run event records for key lifecycle milestones and failures.
- Add idempotency guardrails for retries/duplicate deliveries.

## Expected changes

- Worker loop and queue modules (`app/queue/*`) refactored to use Supabase adapter.
- Run and event writebacks in success/failure paths.
- Failure path captures normalized error message for UI/history use later.

## Acceptance criteria

- Worker can consume Supabase queue messages end-to-end.
- Successful runs write completion state and result payload metadata.
- Failed runs write failure state and error event.
- Duplicate processing is prevented or safely no-op with clear logs.

## Out of scope

- User-facing activity history UI.

## Dependencies

- Requires PR 04.
