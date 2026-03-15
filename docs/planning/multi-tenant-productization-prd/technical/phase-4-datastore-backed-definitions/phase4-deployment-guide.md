# Phase 4 Deployment Guide

This guide walks you through deploying Phase 4 (datastore-backed definitions) to Supabase and performing manual validation afterward.

---

## Prerequisites

- [Supabase CLI](https://supabase.com/docs/guides/cli) installed
- Docker (for local validation; optional for remote-only deploy)
- `envs/local.env` or `envs/prod.env` with required variables (see below)
- Access to your Supabase project (Dashboard or CLI)

### Required Environment Variables

Ensure your deployment environment has:

| Variable | Required | Notes |
|----------|----------|-------|
| `SUPABASE_URL` | Yes | API URL (e.g. `https://<project-ref>.supabase.co`) |
| `SUPABASE_SECRET_KEY` | Yes | Service role key (bypasses RLS; backend only) |
| `SECRET` | Yes | Auth secret for `Authorization` header |
| `NOTION_API_KEY` | Yes | For Notion page creation |
| `ANTHROPIC_TOKEN` | Yes | For Claude step |
| `GOOGLE_PLACES_API_KEY` | Yes | For Places search |
| `ENABLE_BOOTSTRAP_PROVISIONING` | Recommended | Default `1`; seeds catalog and lazy-provisions owner starters |
| `LOCATIONS_ASYNC_ENABLED` | Optional | Default `1`; async mode requires worker |

See `envs/env.template` for the full list.

---

## Part 1: Deploy to Supabase

### Step 1.1: Run Tests Locally (Pre-Flight)

Before pushing migrations, confirm the Phase 4 stack works locally:

```bash
# Start local Supabase (if not already running)
make supabase-start

# Run full test suite (includes Postgres repo tests)
python -m pytest tests/ -v
```

Expect all tests to pass, including `test_postgres_repositories`, `test_postgres_run_repository`, `test_job_definition_service_postgres`, and `test_id_mapping`.

### Step 1.2: Log In and Link Project

```bash
# Log in to Supabase (opens browser)
make supabase-login

# Link CLI to your remote project
make supabase-link
# Or explicitly: make supabase-link SUPABASE_PROJECT_REF=<your-project-ref>
```

`SUPABASE_PROJECT_REF` defaults to the value in your Makefile (e.g. `ngwcqykrmlwlythbkmwn`). Override if needed.

### Step 1.3: Push Migrations

```bash
make supabase-db-push
```

This runs `supabase db push`, applying all migrations in `supabase/migrations/` to the linked remote project. Phase 4 migrations applied in order:

1. `20260312160000_baseline.sql`
2. `20260312160100_phase1_schema_and_queue.sql`
3. `20260313120000_public_pgmq_rpc_wrappers.sql`
4. `20260313130000_phase2_pr01_auth_schema_user_profile_invite_codes.sql`
5. `20260313140000_worker_retry_count.sql`
6. `20260315100000_phase4_pr01_datastore_schema.sql` — Phase 4 schema, RLS, catalog/owner-scoped tables
7. `20260315110000_phase4_pr02_id_mappings.sql` — ID mapping table for nested run records

If migrations have already been applied (e.g. from a previous deploy), the CLI will report no new migrations to run.

### Step 1.4: One-Liner (Link + Push)

```bash
make supabase-deploy
```

Equivalent to `supabase-link` followed by `supabase-db-push`.

---

## Part 2: Deploy the Application

After migrations are applied, deploy your API and worker so they use the remote Supabase project.

1. **Set environment variables** in your hosting platform (Render, Railway, etc.) to point at the remote Supabase:
   - `SUPABASE_URL` — from Supabase Dashboard > Project Settings > API
   - `SUPABASE_SECRET_KEY` — service role key (not anon key)
   - All other required vars from `envs/env.template`

2. **Deploy API and worker** using your normal process (e.g. `git push` to trigger Render deploy).

3. **Ensure both API and worker** use the same env (especially `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SUPABASE_QUEUE_NAME`). The worker must run alongside the API for async locations.

---

## Part 3: Manual Validation (Post-Deploy)

### 3.1 Bootstrap and Definitions Load

1. Start the API (or confirm it’s running in production).
2. Check startup logs for:
   - Catalog seed success (no errors from `PostgresBootstrapProvisioningService.seed_catalog_if_needed`)
   - No mapping consistency errors (ID mapping contract check)
3. With `ENABLE_BOOTSTRAP_PROVISIONING=1`, the first `POST /triggers/{user_id}/locations` will provision owner starter definitions (connector instances, target, trigger, job graph).

### 3.2 Trigger a Job and Inspect Runs

1. Start the worker (if using async mode).
2. Trigger a locations job:
   ```bash
   # Local
   make test-locations
   # Or with custom keywords:
   make test-locations KEYWORDS="coffee shop"
   
   # Remote (replace with your deployed URL and secret)
   make test-remote REMOTE_BASE_URL=https://your-api.onrender.com REMOTE_SECRET=<your-secret> KEYWORDS="stone arch bridge"
   ```
3. Expect `{"status":"accepted","job_id":"..."}` (async) or a full response (sync).
4. Inspect runs in Postgres:
   - **Local:** `make show-runs-db` or `make supabase-dashboard` → SQL Editor
   - **Remote:** Supabase Dashboard → SQL Editor
   ```sql
   SELECT id, owner_user_id, job_id, status, platform_job_id, created_at
   FROM job_runs
   ORDER BY created_at DESC
   LIMIT 20;
   ```

### 3.3 Durable Edits (Optional)

1. Edit a job definition (e.g. via future UI or direct DB update for now).
2. Trigger a run.
3. Restart the API/worker container.
4. Confirm the run used the updated definition and that edits persist across restarts.

### 3.4 RLS and Tenant Isolation (Optional)

- RLS policies enforce `auth.uid() = owner_user_id` on owner-scoped tables.
- To verify: use Supabase Studio with different auth contexts, or run queries as different users.
- See `supabase/migrations/20260315100000_phase4_pr01_datastore_schema.sql` for policy definitions.
- Note: The backend uses `SUPABASE_SECRET_KEY` (service role), which bypasses RLS. RLS matters for direct client access and future multi-tenant UI.

### 3.5 Log Correlation for Debugging

Key log patterns in datastore mode:

| Pattern | Meaning |
|---------|---------|
| `locations_enqueued \| job_id=... run_id=...` | Request accepted, run enqueued |
| `postgres_run_event \| run_id=... event_type=pipeline_started` | Worker began execution |
| `postgres_run_event \| run_id=... event_type=pipeline_succeeded` | Execution completed |
| `worker_persist_*_failed \| job_id=... run_id=...` | Persistence failure |

---

## Troubleshooting

### Migrations fail with "relation already exists"

Migrations may have been partially applied. Check `supabase_migrations.schema_migrations` in the remote DB. If needed, fix schema manually or use `supabase db reset` on a **non-production** project to start clean.

### "The trigger was not found"

- Ensure `ENABLE_BOOTSTRAP_PROVISIONING=1`.
- Confirm the first trigger for that owner has run (lazy provisioning).
- Check `trigger_definitions` for a row with the correct `owner_user_id` and path (e.g. `/locations`).

### "The worker got the message but the job did not execute"

- Check worker logs for payload shape, run idempotency, retry count.
- Verify `SUPABASE_QUEUE_NAME` matches between API and worker.
- Confirm `job_runs` has a row; check `status` and `platform_job_id`.

### Runs not visible in `show-runs-db`

- `show-runs-db` uses `supabase db execute`, which targets the **linked** project. Ensure you’ve run `make supabase-link` for the correct project.
- For remote projects, use Supabase Dashboard → SQL Editor instead.

### YAML run files

Phase 4 runs live in Postgres. `make show-runs` is deprecated; use `make show-runs-db` or Supabase Studio.

---

## Quick Reference

| Task | Command |
|------|---------|
| Deploy migrations | `make supabase-deploy` |
| Show recent runs (local) | `make show-runs-db` |
| Test locations (local) | `make test-locations` |
| Test remote | `make test-remote REMOTE_BASE_URL=... REMOTE_SECRET=...` |
| Open Supabase Studio (local) | `make supabase-dashboard` |
| Run full test suite | `python -m pytest tests/ -v` |

---

## Related Docs

- [Phase 4 Index](./index.md) — Overview and completion definition
- [Runtime Architecture Onboarding](./runtime-architecture-onboarding.md) — End-to-end flow and debugging
- [p4_pr03 Validation](./p4_pr03-validation-observability-tests-and-docs.md) — Validation checklist
