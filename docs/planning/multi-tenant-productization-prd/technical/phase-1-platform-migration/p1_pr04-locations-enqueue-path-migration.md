# p1_pr04 - `/locations` Enqueue Path Migration

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

---

## Manual steps (after implementation)

Run these once after merging this PR to validate the enqueue path migration:

1. **Ensure p1_pr02 and p1_pr03 are complete** (Phase 1 schema, queue, and Supabase config). If not, follow their manual steps first.

2. **Configure Supabase env vars** in `envs/local.env`:
   - `SUPABASE_URL` — API URL (e.g. `https://<project-ref>.supabase.co` or `http://127.0.0.1:54321` for local)
   - `SUPABASE_SECRET_KEY` — Secret key from Supabase Dashboard > Project Settings > API (or service role key from `supabase status` for local)

3. **Start local Supabase** (if using local stack):
   ```bash
   make supabase-start
   ```
   Apply migrations if needed: `make supabase-reset`.

4. **Start app in async mode**:
   ```bash
   make run-async
   ```
   Or `make run` with `LOCATIONS_ASYNC_ENABLED=1` (default).

5. **Trigger POST /locations and capture job_id**:
   ```bash
   make test-locations
   ```
   Or (use your SECRET from `envs/local.env`):
   ```bash
   curl -s -X POST -H "Authorization: dev-secret" -H "Content-Type: application/json" \
     -d '{"keywords":"stone arch bridge minneapolis"}' \
     http://localhost:8000/locations
   ```
   Expect `200` with `{"status":"accepted","job_id":"loc_..."}`. Record the `job_id`.

6. **Verify in Supabase** (via Studio or `psql`):
   - **platform_jobs**: Row exists with `job_id` matching response, `status = 'queued'`, `keywords` matching request.
   - **pipeline_runs**: Row exists with same `job_id`, `status = 'pending'`, and a `run_id` (UUID).
   - **pgmq queue**: Message in `locations_jobs` contains `job_id`, `run_id`, and `keywords` in payload.
     ```sql
     SELECT * FROM public.pgmq_read('locations_jobs', 5, 1);
     ```

7. **Negative checks**:
   - **Empty keywords** returns 400:
     ```bash
     curl -s -X POST -H "Authorization: dev-secret" -H "Content-Type: application/json" \
       -d '{"keywords":""}' http://localhost:8000/locations
     ```
     Expect `400` with detail mentioning "keywords".
   - **Keywords too long** (>300 chars) returns 400.
   - With Supabase unreachable or misconfigured, expect `503` with "Unable to enqueue request" when async is enabled.

8. **Unit tests**:
   ```bash
   make test-api
   ```
   All tests (including `tests/test_locations_route.py`) must pass.

## Verification checklist

Before closing this PR, confirm:

- [ ] `app/routes/locations.py` async path uses `supabase_queue_repository` and `supabase_run_repository` (no in-memory queue).
- [ ] Enqueue flow: `create_job` → `create_run` → `send` with `job_id`, `run_id`, `keywords` in payload.
- [ ] Response shape unchanged: `{ "status": "accepted", "job_id": "loc_..." }`.
- [ ] 503 returned when repos missing or send/create fails; structured logging on success/failure.
- [ ] Sync path (`LOCATIONS_ASYNC_ENABLED=0`) unchanged.
- [ ] Keyword validation (empty, whitespace, max length) still returns 400.
- [ ] `make test-api` passes; `test_post_locations_async_*` tests cover accepted and 503 cases.
- [ ] Manual steps above pass with local Supabase.
