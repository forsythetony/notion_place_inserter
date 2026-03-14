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
| 2026-03-14 | p2_pr07 | Tests, observability, Phase 2 docs: structured invite-route and startup failure logs; backend tests for auth/invite critical paths and logging assertions; Vitest + RTL frontend harness; auth routing and signup tests; Phase 2 doc reconciliation (p2_pr04 CSV workflow, p2_pr06 POST /auth/signup, technical-plan status); render.yaml and README env consistency; Phase 2 index manual validation section. |
| 2026-03-14 | prevalidate invite signup | Backend signup orchestration: POST /auth/signup validates invite before creating auth user; SignupOrchestrationService with compensation (delete orphan on claim failure); frontend uses signUpWithInvitation then signInWithPassword; route and service tests; OpenAPI updated. Validated: invalid codes no longer create auth users; valid signup succeeds. |
| 2026-03-14 | issued_to uniqueness | Idempotent invitation issuance: POST /auth/invitations returns existing row when non-empty issuedTo already exists; get_invitation_by_issued_to repository method; route and repo tests. |
| 2026-03-13 | p2_pr06 | Sign-up with invite code and user type assignment: invite-required signup flow, POST /auth/invitations/claim-for-signup orchestration (claim + profile provisioning), frontend AuthPage invite code field, AuthProvider signup orchestration with session check and claim failure cleanup, deterministic error handling for invalid/already-claimed/race. |
| 2026-03-13 | p2_pr05 | Frontend landing, auth, and dashboard routing: public landing with top-right Sign In/Sign Up, auth page (sign-in/sign-up via Supabase), protected dashboard route, route guards and redirects, minimal dashboard with Run Location Inserter trigger. React Router + Supabase client; .env.example and README updated. |
| 2026-03-13 | p2_pr04 | Manual invitation code generation: helper_scripts/invitation_csv_issuer Typer CLI reads CSV (userType, platformIssuedOn, issueTo), authenticates via Supabase Auth, issues codes via POST /auth/invitations. input_template.csv, .gitignore for input_actual/output, Makefile invite-issue-csv/invite-issue-csv-help. |
| 2026-03-13 | p2_pr03 complete | Marked p2_pr03 complete; issuance/validate/claim validated. Added p2_pr06 note to validate claim logic when integrated into signup. |
| 2026-03-13 | p2_pr03 | Invitation issuance and claim service: admin-only POST /auth/invitations (userType, issuedTo, platformIssuedOn), validate/claim endpoints, require_admin_managed_auth, SupabaseAuthRepository validate/claim/generate_invitation_code, OpenAPI schemas, route and repo tests. |
| 2026-03-13 | p2_pr03-admin-issuance-endpoint-doc-update | Revised PR-03 story to require backend invite issuance endpoint with POST body (`userType`, `issuedTo`, `platformIssuedOn`) and strict admin-only authorization. |
| 2026-03-13 | p2_pr03-doc-update | Updated PR-03 story doc to use temporary script-based invite code issuance and clarified signup claim flow creates backend account when code is valid. |
| 2026-03-13 | worker-network-fd-leak-fix | Implemented primary FD leak fix: reuse single schema-scoped PostgREST client in SupabaseQueueRepository, add close() session cleanup, wire best-effort cleanup into worker_main shutdown. Tests for close() and _cleanup_queue_repo. |
| 2026-03-13 | worker-network-fd-root-cause-findings | Replaced speculative network FD remediation notes with evidence-backed findings tying idle socket growth to repeated `client.schema("public")` queue RPC client creation and missing session cleanup. |
| 2026-03-13 | worker-network-fd-remediation-doc | Added incident remediation playbook for suspected network FD leak, including immediate mitigations, code options, rollout sequence, and validation gates. |
| 2026-03-13 | worker-memory-isolation-hardening | Split worker memory diagnostics from tracemalloc via new env flag, added richer heartbeat fields for root-cause isolation, and hardened terminal failure path to avoid FK persistence rethrow loops. |
| 2026-03-13 | worker-memory-remediation-implementation | Implemented non-retriable classification (23503/23505), read_count ceiling, memory diagnostics (heartbeat, per-message delta, high-watermark tracemalloc), env wiring, and tests. Added manual validation steps to findings doc. |
| 2026-03-13 | tech-debt-story-retry-error-propagation | Added `docs/tech-debt/` and created a backlog story to validate retry-flow error propagation and terminal handling consistency. |
| 2026-03-13 | worker-memory-starvation-investigation-update | Updated incident findings with new log evidence, ranked hypotheses, added memory telemetry plan, and additional mitigation/validation steps. |
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
