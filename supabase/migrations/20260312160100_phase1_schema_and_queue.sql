-- PR-02: Phase 1 Schema and Queue Foundation
-- Durable persistence tables and pgmq queue for async processing and run tracking.

-- ---------------------------------------------------------------------------
-- 1. Enable pgmq extension
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgmq;

-- ---------------------------------------------------------------------------
-- 2. platform_jobs: job metadata and lifecycle
-- ---------------------------------------------------------------------------
CREATE TABLE platform_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id text NOT NULL,
  keywords text,
  status text NOT NULL DEFAULT 'queued',
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  error_message text,
  -- Phase 2 forward-compatible (nullable for now)
  owner_user_id uuid,
  tenant_id uuid,
  CONSTRAINT platform_jobs_job_id_unique UNIQUE (job_id)
);

CREATE INDEX idx_platform_jobs_job_id ON platform_jobs (job_id);
CREATE INDEX idx_platform_jobs_status ON platform_jobs (status);
CREATE INDEX idx_platform_jobs_created_at ON platform_jobs (created_at);

-- ---------------------------------------------------------------------------
-- 3. pipeline_runs: run records linked to jobs
-- ---------------------------------------------------------------------------
CREATE TABLE pipeline_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id text NOT NULL REFERENCES platform_jobs (job_id) ON DELETE CASCADE,
  run_id text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  result_json jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  -- Phase 2 forward-compatible (nullable for now)
  owner_user_id uuid,
  tenant_id uuid,
  CONSTRAINT pipeline_runs_run_id_unique UNIQUE (run_id)
);

CREATE INDEX idx_pipeline_runs_run_id ON pipeline_runs (run_id);
CREATE INDEX idx_pipeline_runs_job_id ON pipeline_runs (job_id);
CREATE INDEX idx_pipeline_runs_status ON pipeline_runs (status);
CREATE INDEX idx_pipeline_runs_created_at ON pipeline_runs (created_at);

-- ---------------------------------------------------------------------------
-- 4. pipeline_run_events: event log per run
-- ---------------------------------------------------------------------------
CREATE TABLE pipeline_run_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id text NOT NULL REFERENCES pipeline_runs (run_id) ON DELETE CASCADE,
  event_type text NOT NULL,
  event_payload_json jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_pipeline_run_events_run_id ON pipeline_run_events (run_id);
CREATE INDEX idx_pipeline_run_events_created_at ON pipeline_run_events (created_at);

-- ---------------------------------------------------------------------------
-- 5. http_triggers: minimal trigger definitions (Phase 1 stub)
-- ---------------------------------------------------------------------------
CREATE TABLE http_triggers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  path text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  -- Phase 2 forward-compatible (nullable for now)
  owner_user_id uuid,
  tenant_id uuid
);

CREATE INDEX idx_http_triggers_path ON http_triggers (path);

-- ---------------------------------------------------------------------------
-- 6. Create locations_jobs queue for durable async processing
-- ---------------------------------------------------------------------------
SELECT pgmq.create('locations_jobs');
