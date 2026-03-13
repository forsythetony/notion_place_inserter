# PR-06 Detailed Deploy Steps (Render + Supabase)

Date: 2026-03-13

This guide provides explicit deployment steps for the selected Phase 1 architecture, managed via Render Blueprints:

- API on Render Web Service (defined in backend `render.yaml`)
- Worker on a second Render Web Service (defined in backend `render.yaml`)
- UI on Render Static Site
- Supabase as queue/data platform

## 1) Prerequisites

Before deploying:

1. Supabase migrations are applied to your target project.
2. You have all required secrets/keys ready:
   - `SECRET`
   - `SUPABASE_URL`
   - `SUPABASE_SECRET_KEY`
   - `NOTION_API_KEY`
   - `ANTHROPIC_TOKEN`
   - `GOOGLE_PLACES_API_KEY`
   - optional: `FREEPIK_API_KEY`, Twilio/WhatsApp vars
3. You know your frontend static-site origin (for backend CORS).

## 1.1) Blueprint + secret file workflow (recommended)

Yes, the intended pattern is:

1. Create/manage an environment group manually in Render (for example: `notion-pipeliner-backend`).
2. Add a secret file to that group:
   - filename: `.env`
   - contents: your production env file
3. Link that environment group to both backend services (API and worker).
4. Keep service topology, commands, and non-secret IaC in `render.yaml`.

Why this pattern:

- Render Blueprint does not define secret file contents in `render.yaml`.
- Secret files remain managed in Render, while service definitions remain managed in source control.
- Both backend services can share the same `/etc/secrets/.env` source of truth.

Example service env section in `render.yaml`:

```yaml
envVars:
  - fromGroup: notion-pipeliner-backend
```

Notes:

- Service-level env vars in Render override group values.
- If API and worker need different values, keep shared values in the group and override per service only where needed.

## 2) Define backend services in Blueprint (`render.yaml`)

Ensure backend `render.yaml` includes both services:

- API service:
  - Build Command: `pip install -r requirements.txt`
  - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Worker service:
  - Build Command: `pip install -r requirements.txt`
  - Start Command: `python -m app.worker_main`

Service names in `render.yaml`: `notion-pipeliner-api`, `notion-pipeliner-worker`.

## 2.1) Migrating from UI-managed to Blueprint-managed

If you already deployed via the Render UI (e.g. `hello-world-api`):

1. Create the environment group `notion-pipeliner-backend` in Render (see 1.1) and add your `.env` secret file.
2. Apply the Blueprint (New -> Blueprint, or sync existing Blueprint) so Render creates `notion-pipeliner-api` and `notion-pipeliner-worker`.
3. Link the env group to both new services (Blueprint does this via `fromGroup` if the group exists).
4. Add any API-only overrides (e.g. `CORS_ALLOWED_ORIGINS`) to the API service or to the env group.
5. Update frontend `VITE_BASE_URL` to the new API URL (`https://notion-pipeliner-api.onrender.com`).
6. Smoke test; then decommission the old `hello-world-api` service.

## 3) Deploy backend via Blueprint

1. **Create environment group first** (if not already done):
   - In Render: **Environment Groups** -> **New Environment Group** -> name: `notion-pipeliner-backend`
   - Add secret file: filename `.env`, contents = your production env (SECRET, SUPABASE_*, provider keys, CORS_ALLOWED_ORIGINS, etc.)
2. In Render Dashboard, click **New -> Blueprint** (or sync existing Blueprint).
3. Select the backend repository and target branch.
4. Render creates `notion-pipeliner-api` and `notion-pipeliner-worker` from `render.yaml`; both link to `notion-pipeliner-backend`.
5. Ensure the env group contains (or add as env vars in the group):
   - `SECRET`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`
   - `NOTION_API_KEY`, `ANTHROPIC_TOKEN`, `GOOGLE_PLACES_API_KEY`
   - optional: `FREEPIK_API_KEY`, Twilio/WhatsApp vars
   - `CORS_ALLOWED_ORIGINS=https://<your-ui>.onrender.com` (API needs this; put in group so both can inherit, or override on API only)
6. Optional worker tuning (in env group or per-service override):
   - `WORKER_POLL_INTERVAL_SECONDS=1`
   - `WORKER_VT_SECONDS=300`
7. Scale worker to at least one running instance.
8. Record API URL:
   - `https://notion-pipeliner-api.onrender.com`

Important: do not manage API/worker manually in a way that drifts from `render.yaml`.

## 4) Deploy UI service (Render Static Site)

Use the frontend repo (`notion_pipeliner_ui`).

1. Preferred: create UI via Blueprint in frontend repo if `render.yaml` exists there.
2. Otherwise create Render Static Site manually.
3. Configure:
   - Build Command: `npm run build`
   - Publish Directory: `dist`
4. Set frontend environment variables:
   - `VITE_BASE_URL=https://notion-pipeliner-api.onrender.com` (or your API URL)
   - `VITE_SECRET=<same value as backend SECRET>`
5. Deploy and record UI URL:
   - `https://<your-ui>.onrender.com`

## 5) Wire CORS (backend API service)

Add to env group `notion-pipeliner-backend` or override on API service:

- `CORS_ALLOWED_ORIGINS=https://<your-ui>.onrender.com`

If you need multiple origins:

- `CORS_ALLOWED_ORIGINS=https://<your-ui>.onrender.com,https://<other-origin>.onrender.com`

Re-apply/redeploy Blueprint after CORS changes.

## 6) Post-deploy smoke tests

### API auth

```bash
curl -H "Authorization: $SECRET" "https://notion-pipeliner-api.onrender.com/"
```

Expected: `200` with hello payload.

### Enqueue path

```bash
curl -X POST \
  -H "Authorization: $SECRET" \
  -H "Content-Type: application/json" \
  -d '{"keywords":"stone arch bridge minneapolis"}' \
  "https://notion-pipeliner-api.onrender.com/locations"
```

Expected: `{"status":"accepted","job_id":"loc_..."}`.

### Worker execution

Check worker logs for:

- startup confirmation (`worker_starting`)
- queue read/process activity
- success/failure log entries for run lifecycle

### UI trigger

From deployed UI:

1. Click `Run Location Inserter`
2. Confirm state transitions:
   - `submitting`
   - then `accepted` (healthy path) or explicit `error` message

## 7) Data-plane validation (Supabase)

In Supabase tables:

- `platform_jobs`: `queued -> running -> succeeded/failed`
- `pipeline_runs`: lifecycle updates and completion metadata
- `pipeline_run_events`: start/success/failure events present

If jobs remain `queued`, worker is likely not running correctly or is misconfigured.

## 8) Troubleshooting checklist

If jobs are not dequeued:

1. Confirm worker service exists in Blueprint and is healthy.
2. Confirm worker start command is exactly:
   - `python -m app.worker_main`
3. Confirm API and worker point to same:
   - `SUPABASE_URL`
   - `SUPABASE_SECRET_KEY`
   - queue name (`SUPABASE_QUEUE_NAME` if overridden)
4. Confirm worker has required provider keys (missing keys can crash worker startup).
5. Confirm Supabase migrations and pgmq wrappers are applied in target project.
6. Confirm API async mode:
   - `LOCATIONS_ASYNC_ENABLED=1`
7. Confirm no typo in env var names (`SECRET`, not `secret`).
8. Confirm backend `render.yaml` includes both API and worker services (and Blueprint sync succeeded).

## 9) Rollback strategy

1. Roll back API and/or worker to previous known-good deploy in Render.
2. Re-point frontend `VITE_BASE_URL` if required.
3. Re-run smoke tests before declaring recovery.

---

## 10) Manual steps checklist (execute in order)

Use this checklist when migrating to Blueprint-managed backend or doing a fresh deploy.

### A. Create environment group (Render Dashboard)

1. Go to **Environment Groups** -> **New Environment Group**.
2. Name: `notion-pipeliner-backend`.
3. Add secret file:
   - Filename: `.env`
   - Contents: paste your production env (SECRET, SUPABASE_URL, SUPABASE_SECRET_KEY, NOTION_API_KEY, ANTHROPIC_TOKEN, GOOGLE_PLACES_API_KEY, CORS_ALLOWED_ORIGINS, etc.).
4. Save the group.

### B. Apply Blueprint (backend repo)

1. **New -> Blueprint** (or sync existing Blueprint).
2. Select backend repo and target branch.
3. Render creates `notion-pipeliner-api` and `notion-pipeliner-worker`.
4. Ensure both services are linked to `notion-pipeliner-backend` (Blueprint does this via `fromGroup` if the group exists; create the group first if needed).
5. Scale worker to at least 1 instance.
6. Record API URL: `https://notion-pipeliner-api.onrender.com`.

### C. Wire frontend

1. In UI service (Static Site), set:
   - `VITE_BASE_URL=https://notion-pipeliner-api.onrender.com`
   - `VITE_SECRET=<same as backend SECRET>`
2. Redeploy UI if needed.

### D. Verify CORS

1. In env group `notion-pipeliner-backend`, ensure `CORS_ALLOWED_ORIGINS` includes your UI origin (e.g. `https://notion-pipeliner-ui.onrender.com`).
2. Redeploy API if you changed the group.

### E. Smoke test

1. `curl -H "Authorization: $SECRET" "https://notion-pipeliner-api.onrender.com/"` -> expect 200.
2. `curl -X POST -H "Authorization: $SECRET" -H "Content-Type: application/json" -d '{"keywords":"stone arch bridge minneapolis"}' "https://notion-pipeliner-api.onrender.com/locations"` -> expect `{"status":"accepted","job_id":"..."}`.
3. Check worker logs for dequeue + pipeline execution.
4. From UI: click **Run Location Inserter** -> expect `accepted` state.

### F. Cutover (if migrating from old service)

1. After smoke tests pass, update frontend `VITE_BASE_URL` to new API URL (if not already done).
2. Decommission old `hello-world-api` (and any old worker) in Render.

