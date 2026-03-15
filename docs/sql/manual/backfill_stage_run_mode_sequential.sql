-- =============================================================================
-- Temporary mitigation: force sequential stage execution for notion_place_inserter
-- =============================================================================
--
-- Context: Reduces DB/socket contention (Errno 11 "Resource temporarily unavailable")
-- when multiple pipelines run in parallel and share a single Supabase client.
-- See: docs/tech-debt/td-2026-03-15-resource-constraints-db-connections-threads.md
--
-- IMPORTANT: This script is intentionally NOT part of versioned schema migrations.
-- Run manually in Supabase Dashboard → SQL Editor when needed.
-- Idempotent: safe to run multiple times.
--
-- =============================================================================

-- Pre-check: current run modes (run first to inspect before update)
SELECT
  owner_user_id,
  job_id,
  id AS stage_id,
  display_name,
  pipeline_run_mode
FROM stage_definitions
WHERE job_id = 'job_notion_place_inserter'
ORDER BY owner_user_id, sequence, id;

-- Idempotent backfill update
UPDATE stage_definitions
SET
  pipeline_run_mode = 'sequential',
  updated_at = now()
WHERE job_id = 'job_notion_place_inserter'
  AND pipeline_run_mode <> 'sequential';

-- Post-check: confirm all sequential (run after update to verify)
SELECT
  owner_user_id,
  job_id,
  id AS stage_id,
  display_name,
  pipeline_run_mode
FROM stage_definitions
WHERE job_id = 'job_notion_place_inserter'
ORDER BY owner_user_id, sequence, id;
