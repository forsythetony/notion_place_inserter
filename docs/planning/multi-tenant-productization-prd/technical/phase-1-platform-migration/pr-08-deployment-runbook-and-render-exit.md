# PR 08 - Deployment Runbook and Render Exit

## Objective

Finalize Phase 1 by documenting and validating the hybrid deployment baseline: Render hosts the runtime (API, worker, UI) while Supabase provides the platform/data plane (Postgres, queue, supporting services).

## Scope

- Document Render + Supabase hybrid deployment model:
  - API and worker on Render Web Service
  - Minimal UI on Render Static Site
  - Supabase for Postgres, pgmq queue, and platform primitives
- Add environment variable matrix for:
  - API process (including `SECRET` for auth header validation; `SUPABASE_URL`, `SUPABASE_SECRET_KEY`)
  - worker process
  - frontend process (e.g. `BASE_URL` for API endpoint)
- Add migration/cutover runbook:
  - pre-cutover checklist
  - cutover steps
  - rollback plan
- **Ops note:** The API reads auth from env var `SECRET` (uppercase). Set `SECRET` in Render Environment or in your `.env` file.

## Render stand-up checklist (executable)

Use this checklist to stand up Phase 1 runtime on Render with Supabase backing services.

### 1) Pre-flight (required before Render changes)

1. Ensure Supabase migrations are applied to target project (`platform_jobs`, `pipeline_runs`, `pipeline_run_events`, queue setup).
2. Confirm secret inventory is ready for deploy:
   - API/worker: `SECRET`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, provider keys (`NOTION_API_KEY`, `ANTHROPIC_TOKEN`, `GOOGLE_PLACES_API_KEY`, optional `FREEPIK_API_KEY`)
   - frontend: `BASE_URL` (points to deployed API URL)
3. Confirm backend supports static-site origin in CORS for the frontend domain you will assign in Render.

### 2) Create or update Render API service (Web Service)

1. In Render dashboard: **New -> Blueprint** (or update existing API service).
2. Point to this repo (`render.yaml` currently defines API baseline).
3. Verify commands:
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. In **Environment**, set required vars. Important: set auth variable name as `SECRET`.
5. Deploy and capture API URL (for frontend `BASE_URL`).

### 3) Create worker process (Web Service)

1. Create a second Render Web Service for worker consumption (same repo/branch).
2. Use same build command as API service.
3. Set start command to the worker entrypoint introduced in PR 05 for Supabase queue consumption.
4. Set worker env vars:
   - `SECRET`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`
   - same provider keys needed by pipeline execution
5. Scale worker instance to at least 1 running instance and confirm process stays healthy.

### 4) Create UI service (Static Site)

1. In Render dashboard: **New -> Static Site**.
2. Configure build/publish settings for the frontend app path added in PR 06.
3. Add frontend env var:
   - `BASE_URL=https://<api-service>.onrender.com`
4. Deploy and record static-site URL.

### 5) Wire CORS and validate browser-to-API path

1. Add static-site origin to backend allowed origins (exact scheme + host).
2. Redeploy API if CORS configuration changed.
3. From deployed UI, click `Run Location Inserter` and verify accepted response state.

### 6) Smoke-test checklist (post-deploy)

1. API auth check:
   - `curl -H "Authorization: $SECRET" "https://<api-service>.onrender.com/"`
   - Expect `200` and hello payload.
2. Enqueue check:
   - `curl -X POST -H "Authorization: $SECRET" -H "Content-Type: application/json" -d '{"keywords":"stone arch bridge minneapolis"}' "https://<api-service>.onrender.com/locations"`
   - Expect accepted payload with `job_id` (async path).
3. Worker check:
   - Confirm worker logs show dequeue + pipeline execution.
4. Persistence check:
   - Confirm run lifecycle writebacks in Supabase tables (`queued/running/succeeded` or `failed`).
5. UI check:
   - Confirm static-site button triggers API and displays idle/submitting/accepted/error states.

### 7) Cutover order

1. Deploy API with Supabase config.
2. Deploy worker and verify dequeue loop health.
3. Deploy static site and set `BASE_URL`.
4. Run smoke tests.
5. Announce cutover once all checks pass.

### 8) Rollback plan

1. If API/worker regressions occur, roll back Render services to previous known-good deploy.
2. Disable frontend traffic to new API path (temporary maintenance page or revert `BASE_URL` to previous endpoint).
3. Keep failed run artifacts for diagnosis; do not drop Supabase data during incident response.
4. Re-run smoke tests on rollback target before declaring recovery.

## Expected changes

- Documentation updates across `README.md` and planning docs.
- Any required deployment config templates/scripts for hybrid flow.
- Clear smoke-test checklist for post-deploy validation.

## Acceptance criteria

- New team member can deploy using docs with Render runtime + Supabase platform.
- Cutover and rollback steps are explicit and executable.
- Phase 1 docs, plan, and runbook are internally consistent.

## Out of scope

- Phase 2 auth rollout or tenant policy implementation.

## Dependencies

- Requires PR 07.
