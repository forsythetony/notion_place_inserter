# Phase 1 Technical Plan: Supabase Platform Migration

Date: 2026-03-12  
Status: Draft (implementation-ready)  
Scope: PRD Phase 1 only (`platform migration`), no end-user auth UX yet

## 1) Goal of this phase

Retain Render-hosted runtime (API, worker, UI) while adopting Supabase as the durable platform/data plane. Phase 1 migrates persistence and queueing to Supabase; it does **not** move API or UI hosting off Render.

- keep the core pipeline execution model (`Stage`, `Pipeline`, `PipelineStep`)
- preserve current `/locations` behavior (accept request and process asynchronously by default)
- stand up a minimal frontend with one button that triggers the same behavior
- establish durable infrastructure primitives needed for later phases (auth, tenancy, persistent run history, secrets)

**Hosting model (Phase 1):**
- **Runtime plane (Render):** FastAPI API + Python worker on Render Web Service; minimal UI on Render Static Site.
- **Platform plane (Supabase):** Postgres (jobs, runs, events), pgmq queue, and supporting platform services.

This phase intentionally does **not** introduce user-facing authentication flows or full multi-tenant UI management. Future migration of runtime hosting to Supabase (e.g. Edge Functions) may be revisited after production metrics and cost review.

## 2) Current-state findings (codebase)

The current codebase is operational but still prototype-shaped:

- **API + auth pattern:** FastAPI with shared secret header auth (`app/main.py`, `app/dependencies.py`)
- **Async model:** in-memory queue and worker loop (`app/queue/*`), non-durable across restarts
- **Persistence:** Notion is the output datastore, but there is no product datastore for jobs/runs/config
- **Hosting:** `render.yaml` and README deploy instructions are Render-specific
- **API contract:** `POST /locations` already supports accepted/enqueued response in async mode (good for queue-backed migration)
- **Observability:** loguru file + console logs exist, but no durable run-event persistence

Implication: Phase 1 should minimize pipeline logic churn and replace platform primitives around it first.

## 3) Supabase capability constraints and design implications

Based on Supabase docs reviewed for Auth, RLS, Queues, Vault, Functions, and CLI:

- **Auth + RLS are first-class**: ideal for Phase 2 tenant isolation, but we can keep Phase 1 API access simple and service-controlled.
- **Queues (`pgmq`) are durable**: direct replacement for in-memory queue semantics.
- **Vault is available**: supports encrypted secret storage from SQL for integration credentials.
- **Edge Functions have runtime limits** (notably request/CPU/memory constraints): this phase should avoid moving all long/heavy Python pipeline execution into Edge Functions immediately.
- **CLI + migrations are mature**: we should establish migration-driven schema management now.

Implication: adopt a **Supabase core + Python worker bridge** for Phase 1 to preserve behavior and reduce rewrite risk.

## 4) Target architecture for Phase 1

### 4.1 Control plane (Supabase-native)

- Supabase Postgres as system-of-record for:
  - job enqueue metadata
  - pipeline run records
  - run events / status transitions
  - trigger definitions (minimal stub for now)
- Supabase Queue (`pgmq`) for durable async jobs
- Supabase Vault for external provider secrets (Notion, Anthropic, Google Places, Twilio) where applicable
- Supabase SQL migrations managed in repo (`supabase/migrations`)

### 4.2 Execution plane (compatibility-first)

- Keep current Python pipeline execution code path in Phase 1.
- Replace in-memory enqueue/dequeue with Supabase queue operations.
- Introduce a dedicated worker process (Python) that:
  - pops queue messages
  - executes existing `PlacesService.create_place_from_query`
  - writes run status/events back to Supabase tables

Rationale: avoids high-risk Python->Deno/TypeScript rewrite during platform migration.

### 4.3 API + frontend baseline (Render-hosted)

- **API:** FastAPI on Render Web Service. Compatibility endpoint remains `POST /locations`
  - request contract unchanged (`{ "keywords": "..." }`)
  - response remains async accepted payload (`{status, job_id}`)
- **Frontend:** Minimal UI on Render Static Site with one button:
  - calls backend API (env-driven `BASE_URL`) with test/dummy payload
  - displays accepted/failure status
  - CORS / allowed-origin configured for static UI to API calls

## 5) Data model slice for Phase 1

Phase 1 schema is intentionally minimal but forward-compatible with multi-tenancy:

- `platform_jobs`
  - `id` (uuid), `job_id` (text unique), `keywords`, `status`, `created_at`, `started_at`, `completed_at`, `error_message`
- `pipeline_runs`
  - `id` (uuid), `job_id` (fk), `run_id` (text unique), `status`, `result_json`, `created_at`, `completed_at`
- `pipeline_run_events`
  - `id`, `run_id` (fk), `event_type`, `event_payload_json`, `created_at`
- `http_triggers` (minimal)
  - `id`, `name`, `path`, `enabled`, `created_at`

Phase-2-ready columns to include now (nullable in Phase 1):

- `owner_user_id uuid` (references `auth.users(id)` later)
- `tenant_id uuid` (future workspace model)

## 6) Security posture for Phase 1

Because user login is out of scope in this phase:

- Keep server-to-server secret authorization for the compatibility endpoint.
- Use Supabase service credentials only in trusted backend/worker environments.
- Do **not** expose service-role keys in frontend code.
- Enable RLS on product tables now but start with restrictive service-role access only; add user policies in Phase 2.
- Move high-risk provider credentials to Vault or platform secret manager before production cutover.

## 7) Workstreams and implementation sequence

### Workstream A - Supabase project/bootstrap

1. Create Supabase project (dev + prod projects if possible).
   - Current dev project: org `LucidPath Solutions`, ref `ngwcqykrmlwlythbkmwn`
2. Add `supabase/` project config to repository.
3. Initialize migration workflow and baseline migration.
4. Create Phase 1 tables and indexes.
5. Enable `pgmq` extension and create queue(s), e.g. `locations_jobs`.

Deliverables:

- `supabase/config.toml`
- initial SQL migrations in `supabase/migrations`
- queue created and testable via SQL/RPC

### Workstream B - Queue and run-persistence integration (backend)

1. Add Supabase client integration to backend service layer.
2. Replace `app/queue/create_location_queue` + enqueue logic with queue send operation.
3. Add run/job persistence writes at enqueue/start/success/failure lifecycle points.
4. Update worker loop to consume from Supabase queue instead of in-memory queue.

Deliverables:

- durable queue-backed `/locations` flow
- persistent run state in Postgres
- idempotency strategy for message retries (at least run_id/job_id uniqueness + status checks)

### Workstream C - Compatibility API hardening

1. Preserve current request/response contract for `/locations`.
2. Keep synchronous fallback mode for local debugging (optional env switch).
3. Ensure error mapping remains stable (`400`, `503`, `500` semantics as applicable).
4. Update `openapi.yaml` to include durable queue semantics and run tracking metadata.

Deliverables:

- backward-compatible endpoint behavior
- updated API docs for new platform-backed execution path

### Workstream D - Minimal frontend (Render Static Site)

1. Create simple frontend app with one action button (`Run Location Inserter` with dummy payload).
2. Deploy UI to Render Static Site; wire `BASE_URL` (API service URL) via environment.
3. Wire frontend call to migrated API endpoint; ensure CORS allows static origin.
4. Display basic request state (`idle`, `submitting`, `accepted`, `error`).

Deliverables:

- deployable frontend URL (Render Static Site)
- manually validated end-to-end trigger from UI

### Workstream E - Deployment and operations (Render + Supabase hybrid)

1. Document Render runtime + Supabase platform deployment model (API/worker on Web Service, UI on Static Site).
2. Define environment variable matrix for:
   - API process (including `secret` for auth; `SUPABASE_URL`, `SUPABASE_SECRET_KEY` for platform)
   - worker process
   - frontend process (e.g. `BASE_URL` for API endpoint)
3. Add smoke checks for:
   - enqueue success
   - worker dequeue and execution
   - status writeback
   - Notion page creation / dry-run behavior

Deliverables:

- deployment runbook for hybrid model
- updated `README.md` and environment documentation

## 8) Acceptance criteria for Phase 1 completion

Phase 1 is complete when all are true:

1. `POST /locations` no longer depends on in-memory queue for production flow.
2. Jobs survive service restarts (durable queue).
3. Run lifecycle is queryable from Supabase tables.
4. Minimal frontend (Render Static Site) can trigger the endpoint successfully.
5. Deployment runbook documents Render runtime (API/worker/UI) + Supabase platform integration.
6. No major regressions in existing place-insertion behavior versus current baseline.

## 9) Risks and mitigations

- **Risk:** Queue consumer reliability/duplication issues  
  **Mitigation:** enforce idempotency by `run_id`/`job_id`, explicit status transitions, and retry-safe writes.

- **Risk:** Scope creep into Phase 2 auth work  
  **Mitigation:** keep frontend access simple for this phase; only add auth scaffolding that does not block current endpoint parity.

- **Risk:** Worker hosting and process stability  
  **Mitigation:** treat worker as explicit deployable unit on Render Web Service; use stable long-running process support.

- **Risk:** Secret sprawl across env files and platform settings  
  **Mitigation:** centralize secret inventory and move critical tokens to Vault/managed secrets before production cutover.

- **Risk:** Edge Function runtime limits if used for heavy processing  
  **Mitigation:** use Edge/HTTP layer for orchestration, keep heavy pipeline execution in worker process for now.

## 10) Test plan (Phase 1)

- Unit tests:
  - queue adapter behavior (send/read/ack semantics)
  - run status persistence transitions
- Integration tests:
  - `/locations` -> queued job -> worker execution -> run success persisted
  - failure path writes error event and failed status
- Manual smoke tests:
  - frontend button triggers accepted job
  - successful Notion write in normal mode
  - deterministic dry-run output in dry-run mode

## 11) Out of scope (explicitly deferred)

- End-user sign-up/login/logout UX
- Tenant-aware RLS policies for user-visible data access
- Full pipeline builder UI
- Datastore-backed editable trigger/pipeline definitions

## 12) Handoff to Phase 2

At Phase 1 completion, the platform should already have:

- Supabase-backed durable data + queue primitives
- run/event persistence foundation
- frontend-to-backend baseline interaction

Phase 2 can then focus primarily on:

- Supabase Auth session flows in UI/backend
- user ownership fields becoming required
- production RLS policies for user-scoped access
