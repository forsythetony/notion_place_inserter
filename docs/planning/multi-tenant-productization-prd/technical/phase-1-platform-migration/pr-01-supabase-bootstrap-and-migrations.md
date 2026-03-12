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
