# p1_pr05 Manual Test Walkthrough

Run these steps to validate the worker consumer and run lifecycle persistence.

## Prerequisites

- Supabase configured in `envs/local.env` (SUPABASE_URL, SUPABASE_SECRET_KEY)
- API keys: NOTION_API_KEY, ANTHROPIC_TOKEN, GOOGLE_PLACES_API_KEY

## Step 1: Start API and Worker (two terminals)

**Terminal A – API:**
```bash
cd notion_place_inserter
make run
# or: make run-async
```

**Terminal B – Worker:**
```bash
cd notion_place_inserter
make run-worker
```

Wait until both are running. You should see `worker_starting` in the worker log.

---

## Step 2: POST /locations (async enqueue)

```bash
curl -s -X POST -H "Authorization: dev-secret" -H "Content-Type: application/json" \
  -d '{"keywords":"stone arch bridge minneapolis"}' \
  http://localhost:8000/locations
```

**Expected:** `200` with `{"status":"accepted","job_id":"loc_..."}`. Record the `job_id`.

---

## Step 3: Verify worker consumes and persists

In **Terminal B** (worker), you should see logs like:

- `worker_queue_read` (or similar) when a message is read
- `Pipeline executed successfully!` on success
- Or `Pipeline failed for job loc_...` on failure

Within a few seconds the job should move from `queued` → `running` → `succeeded` (or `failed`).

---

## Step 4: Verify DB state (Supabase Studio or script)

**Option A – Supabase Studio**

1. Open your project at https://supabase.com/dashboard
2. Table Editor → `platform_jobs`: find row with your `job_id`, confirm `status = 'succeeded'` (or `failed`)
3. Table Editor → `pipeline_runs`: find row with same `job_id`, confirm `status = 'succeeded'` and `result_json` populated
4. Table Editor → `pipeline_run_events`: find rows with that `run_id`, confirm `pipeline_started`, `pipeline_succeeded` (or `pipeline_failed`)

**Option B – Verification script**

```bash
python scripts/verify_pr05_manual.py <job_id>
```

Example:
```bash
python scripts/verify_pr05_manual.py loc_9196b4ef01a3409eaa193f0f4cb95e77
```

---

## Step 5: Negative / edge-case checks

**Empty keywords (400):**
```bash
curl -s -X POST -H "Authorization: dev-secret" -H "Content-Type: application/json" \
  -d '{"keywords":""}' http://localhost:8000/locations
```
Expected: `400` with detail mentioning "keywords".

**Sync mode (LOCATIONS_ASYNC_ENABLED=0):**

1. Stop API and worker.
2. Run: `make run-sync`
3. POST /locations – response should be the full pipeline result (Notion page), not `{status: "accepted"}`.
4. No worker needed; pipeline runs inline.

---

## Step 6: Idempotency (optional)

1. Enqueue a job, note `job_id` and `run_id` (from DB or logs).
2. Manually re-insert a message into the queue with same `job_id`/`run_id` (or wait for pgmq redelivery after vt).
3. Worker should log `worker_duplicate_skip` and archive without re-executing.

---

## Checklist

- [ ] POST /locations returns 200 with `job_id`
- [ ] Worker consumes message and runs pipeline
- [ ] `platform_jobs` status: queued → running → succeeded (or failed)
- [ ] `pipeline_runs` status: pending → running → succeeded (or failed)
- [ ] `pipeline_run_events` has pipeline_started, pipeline_succeeded (or pipeline_failed)
- [ ] Sync mode (`make run-sync`) still runs inline
- [ ] Empty keywords returns 400
