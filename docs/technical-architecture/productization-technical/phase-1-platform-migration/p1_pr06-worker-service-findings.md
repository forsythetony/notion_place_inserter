# p1_pr06 Worker Service Findings

Date: 2026-03-13

## Question 1: Is a separate worker service necessary in the selected design?

Short answer: **Yes, for the architecture we selected and documented for Phase 1.**

### Why (from docs + code)

- The Phase 1 technical plan explicitly defines:
  - API and worker as separate runtime units on Render Web Services.
  - A dedicated Python worker that dequeues from Supabase `pgmq` and executes the pipeline.
- `POST /locations` only enqueues and returns accepted in async mode; it does not process jobs inline:
  - `app/routes/locations.py` enqueues with `queue_repo.send(...)` and returns `{"status":"accepted","job_id":...}`.
- The dequeue/poll loop exists in a separate worker loop:
  - `app/queue/worker.py` continuously reads queue messages and processes lifecycle transitions.
- The deploy runbook also instructs creation of a second Render Web Service for the worker:
  - `docs/technical-architecture/productization-technical/phase-1-platform-migration/p1_pr08-deployment-runbook-and-render-exit.md`

### Could polling run in the same API service?

**Technically possible, but not the selected design**. You could embed the poller into API startup and run both in one process, but this is not currently implemented and introduces tradeoffs:

- Couples API availability and worker throughput/scaling.
- Can accidentally run multiple pollers when API replicas scale out.
- Makes deployment/restart behavior less predictable for long-running background execution.
- Diverges from the documented Phase 1 architecture and runbooks.

For the current ticket/design baseline, treat worker as a separate process/service.

## Question 2: If worker is necessary, how do we deploy it? New Render service? New repo?

Short answer:
- **Yes, create a new Render Web Service** for the worker.
- **No, you do not need a new repository**.

Use the **same backend repository/branch** as the API service, but with a different start command.

## Recommended Render deployment steps (worker)

1. In Render, create a new **Web Service** (same repo + branch as API).
2. Build command: `pip install -r requirements.txt` (same as API).
3. Start command: `python -m app.worker_main`.
4. Set environment variables to match API (at minimum):
   - `SECRET`
   - `SUPABASE_URL`
   - `SUPABASE_SECRET_KEY`
   - `NOTION_API_KEY`
   - `ANTHROPIC_TOKEN`
   - `GOOGLE_PLACES_API_KEY`
   - Optional: `FREEPIK_API_KEY`, Twilio/WhatsApp vars, worker tuning vars
5. Ensure queue-related settings match API:
   - `SUPABASE_QUEUE_NAME` (if overridden)
   - Same Supabase project credentials
6. Scale to at least one running instance.
7. Validate:
   - Trigger `POST /locations` from UI/API.
   - Worker logs show queue read + processing.
   - `platform_jobs` transitions `queued -> running -> succeeded/failed`.

## Why jobs can appear "stuck queued" after UI/API deploy

Most common causes:

- Worker service missing or not running.
- Worker start command not set to `python -m app.worker_main`.
- Worker env vars missing or different from API.
- API/worker pointing to different Supabase projects.
- Queue name mismatch (`SUPABASE_QUEUE_NAME`).
- Migrations/pgmq setup not applied in target Supabase project.

