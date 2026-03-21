-- Persist per-step processing lines (parallel to pipeline_step PROCESSING logs)
ALTER TABLE step_runs ADD COLUMN IF NOT EXISTS processing_log jsonb NOT NULL DEFAULT '[]'::jsonb;
