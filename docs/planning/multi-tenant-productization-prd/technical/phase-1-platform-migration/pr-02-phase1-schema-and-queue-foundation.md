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

---

## Schema notes (Phase 1 entities)

| Table | Purpose |
|-------|---------|
| `platform_jobs` | Job metadata and lifecycle (keywords, status, timestamps). `job_id` unique for idempotency. |
| `pipeline_runs` | Run records linked to jobs. `run_id` unique for idempotency. FK to `platform_jobs`. |
| `pipeline_run_events` | Event log per run (event_type, event_payload_json). FK to `pipeline_runs`. |
| `http_triggers` | Minimal trigger definitions (name, path, enabled). Phase 1 stub. |

All tables include nullable `owner_user_id` and `tenant_id` for Phase 2 multi-tenancy.

---

## Manual steps (after implementation)

Run these once after merging this PR to validate the schema and queue:

1. **Ensure PR-01 bootstrap is complete** (Supabase stack runs, migrations apply). If not, follow PR-01 manual steps first.

2. **Start the local Supabase stack** (if not already running):
   ```bash
   make supabase-start
   ```

3. **Apply migrations from scratch**:
   ```bash
   make supabase-reset
   ```
   Confirm no migration errors. Both `*_baseline.sql` and `*_phase1_schema_and_queue.sql` should apply.

4. **Verify Phase 1 tables exist** (via Supabase Studio or `psql`):
   ```sql
   SELECT tablename FROM pg_tables WHERE schemaname = 'public'
     AND tablename IN ('platform_jobs', 'pipeline_runs', 'pipeline_run_events', 'http_triggers');
   ```
   Expect 4 rows.

5. **Verify pgmq extension and queue**:
   ```sql
   SELECT * FROM pg_extension WHERE extname = 'pgmq';
   SELECT * FROM pgmq.list_queues() WHERE queue_name = 'locations_jobs';
   ```
   Expect extension installed and `locations_jobs` queue present.

6. **Queue send/pop smoke test**:
   ```sql
   SELECT * FROM pgmq.send('locations_jobs', '{"test": "payload"}');
   SELECT * FROM pgmq.read('locations_jobs', 5, 1);
   ```
   Expect one message sent and one message read with matching payload. Optionally `pgmq.archive()` or `pgmq.delete()` to clean up.

7. **Duplicate constraint smoke test**:
   ```sql
   INSERT INTO platform_jobs (job_id, keywords, status) VALUES ('dup-test', 'foo', 'queued');
   INSERT INTO platform_jobs (job_id, keywords, status) VALUES ('dup-test', 'bar', 'queued');
   ```
   Second insert must fail with unique violation on `job_id`.

   ```sql
   INSERT INTO platform_jobs (job_id, keywords, status) VALUES ('run-parent', 'foo', 'queued');
   INSERT INTO pipeline_runs (job_id, run_id, status) VALUES ('run-parent', 'run-1', 'pending');
   INSERT INTO pipeline_runs (job_id, run_id, status) VALUES ('run-parent', 'run-1', 'pending');
   ```
   Second `pipeline_runs` insert must fail with unique violation on `run_id`.

8. **Stop the stack** when done:
   ```bash
   make supabase-stop
   ```

## Verification checklist

Before closing this PR, confirm:

- [ ] `supabase/migrations/` contains `*_phase1_schema_and_queue.sql` (or equivalent Phase 1 migration).
- [ ] `make supabase-reset` applies migrations cleanly on local Supabase.
- [ ] Four Phase 1 tables exist: `platform_jobs`, `pipeline_runs`, `pipeline_run_events`, `http_triggers`.
- [ ] `pgmq` extension is enabled and `locations_jobs` queue exists.
- [ ] Queue supports send and read (manual smoke test passes).
- [ ] Duplicate `job_id` and `run_id` inserts are rejected by constraints.
- [ ] No API route or worker logic changes were introduced (PR-02 scope).
