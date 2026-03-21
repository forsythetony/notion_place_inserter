-- Add result_json column to job_runs for persisting live-test output
-- (cache values, properties, etc.) without requiring a separate table.
ALTER TABLE job_runs ADD COLUMN IF NOT EXISTS result_json jsonb;
