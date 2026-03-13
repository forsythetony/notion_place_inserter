# p1_pr03 - Backend Supabase Config and Client Layer

## Objective

Add backend infrastructure code needed to talk to Supabase safely from FastAPI and worker processes, without changing request behavior yet.

## Scope

- Add Supabase-related environment configuration:
  - project URL
  - service credential/key for trusted backend contexts
  - queue/table names
- Create a small service/repository layer for:
  - queue operations (send/read/archive via public wrapper RPC abstraction)
  - job/run/event persistence operations
- Add startup validation for required Supabase env vars (similar to existing required provider keys).

## Expected changes

- New backend modules under `app/services/` or `app/integrations/` for Supabase interaction.
- Config constants and typed helpers for environment parsing.
- No route contract changes yet.

## Acceptance criteria

- App starts with clear errors when Supabase env vars are missing/malformed.
- Supabase adapter functions can be called from unit tests with mocks/fakes.
- Existing non-Supabase behavior remains unchanged.

## Out of scope

- Switching `/locations` enqueue path or worker consumer path.

## Dependencies

- Requires PR 02.

---

## Manual steps (after implementation)

Run these once after merging this PR to validate the Supabase config and client layer:

1. **Ensure p1_pr02 is complete** (Phase 1 schema and queue exist). If not, follow p1_pr02 manual steps first.

2. **Configure Supabase env vars** in `envs/local.env`:
   - `SUPABASE_URL` — API URL (e.g. `https://<project-ref>.supabase.co`)
   - `SUPABASE_SECRET_KEY` — Secret key from Supabase Dashboard > Project Settings > API

   For local Supabase, use `supabase status` to get the API URL and anon/service_role key.

3. **Startup validation — missing URL**:
   ```bash
   set -a && source envs/local.env && set +a
   unset SUPABASE_URL
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   Expect app to fail with a clear error mentioning `SUPABASE_URL` and "required". (Or temporarily comment out `SUPABASE_URL` in `envs/local.env` and run `make run`.)

4. **Startup validation — missing secret key**:
   ```bash
   set -a && source envs/local.env && set +a
   unset SUPABASE_SECRET_KEY
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   Expect app to fail with a clear error mentioning `SUPABASE_SECRET_KEY` and "required".

5. **Startup validation — malformed URL**:
   ```bash
   SUPABASE_URL=http://insecure.example.com SUPABASE_SECRET_KEY=key make run
   ```
   Expect app to fail with a clear error mentioning `https` and `SUPABASE_URL`.

6. **Successful startup** (with valid env from `envs/local.env`):
   ```bash
   make run
   ```
   Expect app to start without Supabase-related errors. Existing routes (e.g. `POST /locations`) should behave unchanged.

7. **Repository smoke test** (optional; requires local Supabase running):
   - Start local Supabase: `make supabase-start`
   - Get local API URL and service role key from `supabase status`
   - Set `SUPABASE_URL` and `SUPABASE_SECRET_KEY` in `envs/local.env` for the local project
   - Run app: `make run`
   - Verify `app.state.supabase_client`, `app.state.supabase_queue_repository`, and `app.state.supabase_run_repository` are set (e.g. via a debugger or a one-off script that imports the app after startup)

8. **Unit tests**:
   ```bash
   make test-api
   ```
   All tests (including new Supabase config and repository tests) must pass.

## Verification checklist

Before closing this PR, confirm:

- [ ] `app/integrations/supabase_config.py` exists with typed config and validation.
- [ ] `app/integrations/supabase_client.py` exists with client factory.
- [ ] `app/services/supabase_queue_repository.py` exists with send/read/archive methods (calls public wrapper RPC).
- [ ] `app/services/supabase_run_repository.py` exists with job/run/event persistence methods.
- [ ] App startup validates `SUPABASE_URL` and `SUPABASE_SECRET_KEY`; clear errors when missing/malformed.
- [ ] Supabase adapters are stored on `app.state`; no route/worker logic uses them yet.
- [ ] Unit tests for config, queue repo, and run repo pass (with mocks/fakes).
- [ ] `make test-api` passes; existing route behavior unchanged.
- [ ] `envs/env.template` documents required Supabase vars and optional overrides.
