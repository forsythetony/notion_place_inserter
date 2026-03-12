# PR 01 - Supabase Bootstrap and Migrations

## Objective

Create the Supabase project scaffolding in-repo and establish migration-driven workflow as the only approved path for schema changes.

## Scope

- Add `supabase/` directory and baseline config.
- Document local Supabase CLI workflow (init/start/reset/migration).
- Add first baseline migration file (no app tables yet, just scaffold/baseline if needed).
- Add Makefile targets for migration workflow convenience.

## Expected changes

- Repository structure:
  - `supabase/config.toml`
  - `supabase/migrations/*_baseline.sql` (or equivalent bootstrap migration)
- Docs updates (where appropriate):
  - local setup section for Supabase CLI
  - migration commands and team workflow conventions

## Acceptance criteria

- A developer can run local Supabase stack and apply migrations from a clean checkout.
- Migration files are versioned and reviewed via PRs.
- Team has one canonical way to create/apply schema changes.

## Out of scope

- Product tables, queue setup, or API code changes.

## Dependencies

- None (first PR in sequence).

---

## Manual steps (after implementation)

Run these once after merging this PR to validate the setup:

1. **Install Supabase CLI** (if not already installed):
   ```bash
   brew install supabase/tap/supabase
   # or: npm install -g supabase
   ```

2. **Ensure Docker is running** (required for local Supabase stack).

3. **Link this repo to the hosted Supabase project**:
   - Org: `LucidPath Solutions`
   - Project ref: `ngwcqykrmlwlythbkmwn`
   ```bash
   supabase link --project-ref ngwcqykrmlwlythbkmwn
   ```

4. **Set local environment values** (for app/config consistency):
   ```bash
   # envs/local.env
   SUPABASE_PROJECT_REF=ngwcqykrmlwlythbkmwn
   SUPABASE_URL=https://ngwcqykrmlwlythbkmwn.supabase.co
   ```

5. **Start the local Supabase stack**:
   ```bash
   make supabase-start
   ```
   Wait for services to be healthy. Note the API URL, DB URL, and Studio URL from the output.

6. **Apply migrations** (runs automatically on first start; to reapply from scratch):
   ```bash
   make supabase-reset
   ```

7. **Create a test migration** (optional, to verify workflow):
   ```bash
   make supabase-migration-new NAME=test_scaffold
   ```
   Confirm a new file appears in `supabase/migrations/` with format `YYYYMMDDHHmmss_test_scaffold.sql`. You may delete this file if it was only for verification.

8. **Stop the stack** when done:
   ```bash
   make supabase-stop
   ```

## Verification checklist

Before closing this PR, confirm:

- [ ] `make help` shows Supabase targets (`supabase-start`, `supabase-stop`, `supabase-status`, `supabase-reset`, `supabase-migration-new`).
- [ ] `supabase/config.toml` exists and is committed.
- [ ] `supabase/migrations/` contains at least one migration file (e.g. `*_baseline.sql`).
- [ ] `make supabase-start` brings up the local stack without errors.
- [ ] `make supabase-reset` applies migrations cleanly.
- [ ] A fresh clone can follow the README Supabase section end-to-end.
- [ ] No product tables, queue setup, or API code changes were introduced (PR-02 scope).
