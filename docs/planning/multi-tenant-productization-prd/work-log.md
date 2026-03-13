# Decision Log

A chronological record of decisions and work done during the multi-tenant productization project.

---

## Decisions

Significant decisions with rationale, alternatives considered, and context.

**Format:** Date | Title | Context | Options considered | Decision | Consequences

<!-- Add new entries at the top, most recent first -->

### 2026-03-12 - Select Supabase as Phase 1 platform foundation

- **Date** — 2026-03-12
- **Title** — Supabase-first platform migration (Phase 1)
- **Context** — The PRD required establishing a durable baseline for backend APIs, datastore, async processing, and future auth/tenant isolation. The current codebase relies on shared-secret auth and in-memory queueing, which are not sufficient for productization. Phase 1 keeps the API/worker runtime on Render; Supabase provides the data/control plane.
- **Options considered** —
  1. Supabase-centric platform with queue + Postgres foundation
  2. Firebase + Cloud Run + Cloud SQL
  3. Clerk + Neon + Vercel (+ separate jobs platform)
  4. Keep Render-centric architecture for initial productization
- **Decision** — Use a Supabase-first architecture for Phase 1. Implement durable queueing and run persistence in Supabase Postgres (`pgmq` + SQL migrations), keep the existing Python execution engine as a worker for compatibility, and ship a minimal frontend that calls the migrated endpoint. Defer end-user auth UX and tenant policy enforcement to Phase 2. **Runtime hosting:** API and worker remain on Render Web Service; minimal UI on Render Static Site; Supabase is the platform/data plane.
- **Consequences** —
  - Positive: aligns with PRD direction toward one ecosystem for data/auth; enables durable async jobs, run history, and a clean path to RLS-based tenant isolation.
  - Trade-off: introduces a hybrid architecture (Supabase control plane + Render-hosted Python API/worker/UI) instead of an immediate full rewrite to Supabase Edge Functions.
  - Follow-up: create migration-runbook and queue adapter, then replace in-memory queue dependency in `/locations` path.

---

## Log

Work completed. Add entries at the top, most recent first.

| Date | Ticket / Task | Summary |
|------|---------------|---------|
| 2026-03-13 | p2_pr02 validation | Manual validation complete: missing/invalid auth → 401, valid token → 200 with user_type, stability across repeated calls, API docs verified. |
| 2026-03-13 | worker-retry-backoff | Bounded worker retries with configurable backoff (5,30,60s default); platform_jobs.retry_count migration; final failure marks job/run failed and archives; WORKER_RETRY_DELAYS_SECONDS env; tests. |
| 2026-03-13 | worker-memory-starvation-investigation | Investigated worker memory starvation using Render chart and runtime logs; documented evidence, likely poison-message retry loop root cause, and remediation plan. |
| 2026-03-13 | p2_pr02 | Backend auth context: Bearer validation, AuthContext, GET /auth/context, SupabaseAuthRepository wiring, tests, OpenAPI BearerAuth, deprecation notes. |
| 2026-03-13 | PR-01 complete | Marked PR-01 (auth schema, user_profiles, invitation_codes) as complete; proceeding to PR-02. |
| 2026-03-13 | Supabase local auth runtime fix | Upgraded Supabase CLI (2.75.0 -> 2.78.1), restarted local stack, verified `/auth/v1/admin/users` succeeds, and cleaned diagnostic test users from `auth.users`. |
| 2026-03-13 | Supabase local auth config hardening | Standardized local auth/studio host usage to `localhost` (`supabase-dashboard`, `auth.site_url`, redirect allow-list), restarted stack, and re-verified behavior. |
| 2026-03-13 | Supabase local auth troubleshooting | Investigated local user-creation failures; confirmed `/auth/v1/admin/users` `bad_jwt` rejection while `/auth/v1/signup` succeeds; documented findings and remediation suggestions. |
| 2026-03-13 | PR-01 | Phase 2 auth schema: user_type_enum, user_profiles, invitation_codes tables; migration, SupabaseAuthRepository, config/env defaults, tests, schema docs. |
| 2026-03-13 | Phase 2 manual validation steps | Added explicit "Manual validation steps (after implementation)" and verification checklists to each Phase 2 PR story doc (`pr-01` through `pr-07`). |
| 2026-03-13 | Phase 2 story breakdown | Created Phase 2 PR-sized technical story set (`pr-01` to `pr-07`) with ordered dependency index and retained a phase technical-plan document in `technical/phase-2-authentication-segmentation/`. |
| 2026-03-13 | Phase 2 auth planning updates | Expanded Phase 2 scope with landing/auth/dashboard UX, user-type enum (`ADMIN`, `STANDARD`, `BETA_TESTER`), invite-code lifecycle/data model, and manual code-generation script requirement; added dedicated Phase 2 technical plan doc. |
| 2026-03-13 | PR-08 | Deployment runbook and Render exit: canonical PR-08 runbook with env matrix, cutover/rollback/Render-exit steps; README points to PR-08; PR-06/technical-plan aligned; Phase 1 docs consistent. |
| 2026-03-13 | PR-07 | Tests, observability, API docs: enqueue persistence-failure tests; worker idempotency (failed-run), queue-read and persist-error resilience; correlation logging (job_id+run_id) in worker/subscriber/communicator; openapi.yaml durable queue wording. |
| 2026-03-13 | Keywords textbox UI | Replaced hardcoded locations keywords with user-editable textbox; trim/non-empty and max-300 validation; Run disabled when invalid/loading. |
| 2026-03-13 | PR-06 Blueprint migration | Backend render.yaml: notion-pipeliner-api + notion-pipeliner-worker, fromGroup notion-pipeliner-backend; deploy doc migration steps and manual checklist; README aligned. |
| 2026-03-13 | PR-06 | Minimal frontend trigger UI: finalized error handling (401, network/CORS, VITE_BASE_URL), render.yaml for Render Static Site, env/deploy docs, Phase-1 doc consistency (VITE_BASE_URL/VITE_SECRET). |
| 2026-03-13 | PR-05 | Worker consumer and run lifecycle persistence: Supabase queue read/archive, pipeline execution, queued→running→succeeded/failed transitions, pipeline_run_events, idempotency guardrails, dedicated worker_main entrypoint. Validated end-to-end. |
| 2026-03-13 | PR-04 | Completed `/locations` enqueue path migration to Supabase pgmq + run persistence; validated job enqueue from UI |
| 2026-03-13 | Public pgmq RPC wrappers | Switched queue RPC from direct pgmq schema to public wrapper functions (pgmq_send, pgmq_read, pgmq_archive); migration, repo, tests, docs updated |
| 2026-03-13 | PR-06 UI scaffold | Scaffolded notion_pipeliner_ui: Vite React+TS, Run Location Inserter button, POST /locations client, idle/submitting/accepted/error states, .env.example, README, Makefile |
| 2026-03-13 | Frontend deployment decision docs | Documented that frontend uses Vite, deploys to Render Static Site, and lives in a separate repository |
| 2026-03-13 | env_bootstrap static env key list | Replaced regex/template parsing with a static ordered key list from `envs/env.template` for startup env logging |
| 2026-03-12 | SECRET uppercase | Auth env simplified to SECRET only; removed secret remapping; render.yaml, Makefile, docs updated |
| 2026-03-12 | Render .env | App loads .env at startup from .env, /etc/secrets/.env, or envs/local.env; process env overrides file; SECRET→secret compat |
| 2026-03-12 | PR-04 | In progress: `/locations` enqueue path migrated to Supabase pgmq + run persistence (uncommitted on branch `pr-04-locations-enqueue-path-migration`) |
| 2026-03-12 | PR-03 | Backend Supabase config and client layer: `SupabaseQueueRepository`, `SupabaseRunRepository`, startup wiring in `app/main.py` |
| 2026-03-12 | PR-02 | Phase 1 schema and queue: `platform_jobs`, `pipeline_runs`, `pipeline_run_events`, `http_triggers`, pgmq `locations_jobs` queue |
| 2026-03-12 | PR-01 | Supabase bootstrap: `supabase/config.toml`, baseline + Phase 1 migrations, Makefile targets |
