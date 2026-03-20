# Tech Debt Story: Validate Retry Error Propagation Flow

## ID

- `td-2026-03-13-retry-error-propagation-validation`

## Status

- Backlog

## Why this exists

We added bounded retries and are implementing stronger non-retriable handling, but we still need a dedicated deep validation pass to confirm error propagation is correct across all retry and terminal paths.

This is important because incorrect error propagation can:
- mask deterministic failures as retriable,
- produce misleading run/job status in Supabase,
- create hidden poison-message loops,
- and complicate memory-starvation investigations.

## Goal

Verify that worker retry logic propagates, classifies, and persists errors correctly from first failure through terminal handling.

## In Scope

- Validate worker behavior for:
  - retriable failures (transient errors),
  - deterministic non-retriable failures (for example SQLSTATE `23503`),
  - persist-running failures,
  - persist-success failures,
  - final-failure archival/dead-letter behavior.
- Confirm status/event consistency across:
  - `platform_jobs`,
  - `pipeline_runs`,
  - `pipeline_run_events`,
  - queue archive state.
- Confirm logs include enough context to trace one message end-to-end (`msg_id`, `job_id`, `run_id`, attempt, terminal decision/reason).

## Out of Scope

- Re-architecting queue infrastructure.
- Changing product behavior unrelated to retry/error handling.

## Suggested Validation Tasks

1. Build/refresh a scenario matrix of failure classes and expected terminal behavior.
2. Run targeted automated tests for each branch in `app/queue/worker.py`.
3. Run a manual poison-message drill in a non-prod environment.
4. Verify Supabase records match expected state transitions.
5. Verify Render logs clearly show retry vs terminal decisions.
6. Capture follow-up fixes as separate implementation stories if mismatches are found.

## Acceptance Criteria

- For deterministic non-retriable failures, worker does not continue retrying beyond expected policy.
- For retriable failures, retry count and delay behavior match configured policy.
- Final terminal state is reflected consistently across job/run/event records.
- Message is archived/terminalized exactly once (no oscillation).
- A single message timeline can be reconstructed from logs without ambiguity.

## Primary Code Areas to Review

- `app/queue/worker.py`
- `app/services/supabase_run_repository.py`
- `app/services/supabase_queue_repository.py`
- `tests/test_worker_consumer.py`

## Notes

- This story intentionally focuses on validation and confidence-building before additional retry-flow refactors.
