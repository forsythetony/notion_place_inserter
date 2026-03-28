-- Structured per-step error payload for monitoring and degraded outcomes.

ALTER TABLE step_runs
  ADD COLUMN IF NOT EXISTS error_detail jsonb;

COMMENT ON COLUMN step_runs.error_detail IS
  'Structured step error (schema_version, type, message, traceback, failure_policy, etc.)';
