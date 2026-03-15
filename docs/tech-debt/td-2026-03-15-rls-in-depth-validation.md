# Tech Debt Story: RLS In-Depth Validation

## ID

- `td-2026-03-15-rls-in-depth-validation`

## Status

- Backlog

## Why this exists

Phase 4 p4_pr01 added Row Level Security (RLS) policies to owner-scoped and catalog tables. Initial validation confirmed RLS is enabled and policies exist, but we have not yet verified that policies correctly restrict access in practice (e.g., cross-tenant isolation, service-role bypass, authenticated-user behavior).

Without in-depth validation, we risk:
- RLS policies that appear correct but fail to block unauthorized access in edge cases,
- service-role or anon-key usage that inadvertently bypasses intended isolation,
- missing or incorrect `USING`/`WITH CHECK` expressions allowing unintended reads or writes,
- and tenant data leakage when Postgres repositories go live in p4_pr02.

## Goal

Validate RLS policies in depth: confirm that owner-scoped tables enforce tenant isolation, catalog tables allow only intended read access, and service-role usage behaves as expected.

## In Scope

- Write and run tests that insert/select/update/delete as different users and verify RLS blocks cross-tenant access.
- Verify catalog tables (`connector_templates`, `target_templates`, `step_templates`) allow authenticated read but block user writes.
- Verify `app_limits` allows read of global and own rows, and write only of own rows.
- Document expected RLS behavior for each Phase 4 table.
- Add automated tests (SQL or Python) that can run in CI to catch RLS regressions.

## Out of Scope

- Changing RLS policy definitions (unless defects are found).
- Performance tuning of RLS.
- RLS for tables outside the Phase 4 product model.

## Suggested Validation Tasks

1. Create a test script or SQL session that switches `SET ROLE` / uses different `auth.uid()` contexts and exercises each policy.
2. As User A: insert a row in `job_runs`; as User B: attempt SELECT/UPDATE/DELETE on that row; confirm User B gets zero rows or permission denied.
3. As authenticated user: attempt INSERT/UPDATE/DELETE on `connector_templates`; confirm blocked.
4. As authenticated user: SELECT from `connector_templates`; confirm allowed.
5. As authenticated user: SELECT from `app_limits` where `owner_user_id IS NULL`; confirm allowed.
6. As authenticated user: attempt UPDATE on `app_limits` where `owner_user_id IS NULL`; confirm blocked.
7. Document findings and add regression tests to the test suite.

## Acceptance Criteria

- RLS policies are validated with explicit test cases for owner isolation and catalog read-only behavior.
- At least one automated test (or documented manual procedure) exists for RLS regression.
- Any defects found are logged and prioritized for fix.

## Primary Code Areas to Review

- `supabase/migrations/20260315100000_phase4_pr01_datastore_schema.sql`
- Phase 4 tables: `connector_instances`, `data_targets`, `trigger_definitions`, `job_definitions`, `stage_definitions`, `pipeline_definitions`, `step_instances`, `job_runs`, `stage_runs`, `pipeline_run_executions`, `step_runs`, `usage_records`, `app_limits`, `connector_templates`, `target_templates`, `step_templates`

## Notes

- p4_pr01 manual validation confirmed RLS is enabled and policies exist; this story extends that with behavioral verification.
- Consider using Supabase local with `supabase test` or pytest + Supabase client to automate RLS checks.
