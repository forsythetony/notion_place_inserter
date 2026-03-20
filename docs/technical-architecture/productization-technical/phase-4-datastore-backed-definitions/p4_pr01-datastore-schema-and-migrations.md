# p4_pr01 - Datastore Schema and Migrations

## Objective

Establish the Postgres/Supabase schema foundation for Phase 4: owner-scoped tables, foreign keys, indexes, and RLS baselines so Postgres repository implementations have a stable data model.

## Scope

- Create Supabase migrations for the Phase 3 product model tables: `connector_templates`, `connector_instances`, `target_templates`, `data_targets`, `target_schema_snapshots`, `http_triggers`, `job_definitions`, `stage_definitions`, `pipeline_definitions`, `step_templates`, `step_instances`, `job_runs`, `stage_runs`, `pipeline_runs`, `step_runs`, `usage_records`, `app_limits`
- Use relational columns for identity, ownership, foreign keys, status, and sequencing
- Use `jsonb` for flexible payloads: step config, request body schema, input bindings, target schema raw payload, definition snapshots, usage metadata
- Add `owner_user_id` (or equivalent) to all owner-scoped tables
- Add RLS policies based on `auth.uid()` for owner-scoped tables
- Add indexes on owner columns and common foreign keys
- Add check constraints where appropriate (e.g., status enums, non-negative counts)
- Ensure domain and service contracts remain unchanged (Phase 3 continuity)

## Expected changes

- New Supabase migration files in project migrations directory
- Table definitions matching Phase 3 domain model
- RLS enablement and policies on owner-scoped tables
- Indexes for query performance
- No repository implementations or runtime wiring yet

## Acceptance criteria

- All Phase 3 product model entities have corresponding Postgres tables
- RLS is enabled on owner-scoped tables with policies that restrict access by `auth.uid()`
- Foreign key relationships preserve referential integrity
- `jsonb` columns are used for flexible config/snapshot payloads
- Migrations apply cleanly against a fresh Supabase project
- Domain classes and service interfaces are unchanged

## Out of scope

- Postgres repository implementations (p4_pr02)
- Runtime wiring or cutover from YAML
- Secret reference backend migration (Vault/Supabase secrets)
- Data migration from existing YAML (bootstrap seed can be SQL or script)

## Dependencies

- Requires Phase 3 complete (p3_pr01–p3_pr08).
- Requires existing Supabase project and migration tooling (Phase 1).

---

## Manual validation steps (after implementation)

1. Run migrations against a Supabase project (local or remote).
2. Verify all tables exist with expected columns and types.
3. Confirm RLS is enabled and policies are present on owner-scoped tables.
4. Insert a minimal test row and verify RLS restricts access appropriately.
5. Run any existing tests to ensure no regressions from schema changes.

## Verification checklist

- [x] All product model tables exist with correct schema.
- [x] RLS policies enforce owner-scoped access.
- [x] Foreign keys and indexes are in place.
- [x] Migrations apply cleanly.
- [x] Domain and service contracts unchanged.
