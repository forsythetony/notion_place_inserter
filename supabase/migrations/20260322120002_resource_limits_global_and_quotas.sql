-- Resource limits: global row support, inventory + run caps, new-user defaults, atomic enqueue quota RPC.
-- Version 20260322120002 (not 20260322120000): 20260322120000 was already used in schema_migrations by an
-- older user_cohorts migration filename; Supabase keys migrations by numeric prefix only.

-- ---------------------------------------------------------------------------
-- 1. app_limits: surrogate PK, nullable owner (global row), nullable per-field overrides
-- ---------------------------------------------------------------------------

ALTER TABLE app_limits ADD COLUMN IF NOT EXISTS id uuid DEFAULT gen_random_uuid();

UPDATE app_limits SET id = gen_random_uuid() WHERE id IS NULL;

ALTER TABLE app_limits DROP CONSTRAINT app_limits_pkey;

ALTER TABLE app_limits ALTER COLUMN owner_user_id DROP NOT NULL;

ALTER TABLE app_limits ALTER COLUMN max_stages_per_job DROP NOT NULL;
ALTER TABLE app_limits ALTER COLUMN max_pipelines_per_stage DROP NOT NULL;
ALTER TABLE app_limits ALTER COLUMN max_steps_per_pipeline DROP NOT NULL;

ALTER TABLE app_limits ADD COLUMN IF NOT EXISTS max_jobs_per_owner int;
ALTER TABLE app_limits ADD COLUMN IF NOT EXISTS max_triggers_per_owner int;
ALTER TABLE app_limits ADD COLUMN IF NOT EXISTS max_runs_per_utc_day int;
ALTER TABLE app_limits ADD COLUMN IF NOT EXISTS max_runs_per_utc_month int;

ALTER TABLE app_limits ADD CONSTRAINT app_limits_max_jobs_pos CHECK (max_jobs_per_owner IS NULL OR max_jobs_per_owner > 0);
ALTER TABLE app_limits ADD CONSTRAINT app_limits_max_triggers_pos CHECK (max_triggers_per_owner IS NULL OR max_triggers_per_owner > 0);
ALTER TABLE app_limits ADD CONSTRAINT app_limits_max_runs_day_pos CHECK (max_runs_per_utc_day IS NULL OR max_runs_per_utc_day > 0);
ALTER TABLE app_limits ADD CONSTRAINT app_limits_max_runs_month_pos CHECK (max_runs_per_utc_month IS NULL OR max_runs_per_utc_month > 0);

ALTER TABLE app_limits ADD CONSTRAINT app_limits_structural_pos CHECK (
  max_stages_per_job IS NULL OR max_stages_per_job > 0
);
ALTER TABLE app_limits ADD CONSTRAINT app_limits_structural_pipe_pos CHECK (
  max_pipelines_per_stage IS NULL OR max_pipelines_per_stage > 0
);
ALTER TABLE app_limits ADD CONSTRAINT app_limits_structural_step_pos CHECK (
  max_steps_per_pipeline IS NULL OR max_steps_per_pipeline > 0
);

-- Global row (owner_user_id IS NULL) must have all limit columns set (non-null).
ALTER TABLE app_limits ADD CONSTRAINT app_limits_global_complete CHECK (
  owner_user_id IS NOT NULL
  OR (
    max_stages_per_job IS NOT NULL
    AND max_pipelines_per_stage IS NOT NULL
    AND max_steps_per_pipeline IS NOT NULL
    AND max_jobs_per_owner IS NOT NULL
    AND max_triggers_per_owner IS NOT NULL
    AND max_runs_per_utc_day IS NOT NULL
    AND max_runs_per_utc_month IS NOT NULL
  )
);

DROP INDEX IF EXISTS idx_app_limits_global;

-- Single unique index on owner_user_id: one global row (NULL) and one row per user.
-- NULLS NOT DISTINCT (PG15+) lets ON CONFLICT (owner_user_id) match this index (PostgREST upsert).
-- Replaces partial indexes that Postgres could not use as upsert conflict targets (42P10).
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_limits_owner_user_id_unique
  ON app_limits (owner_user_id)
  NULLS NOT DISTINCT;

ALTER TABLE app_limits ALTER COLUMN id SET NOT NULL;

ALTER TABLE app_limits ADD PRIMARY KEY (id);

-- Backfill per-owner rows that lost NOT NULL: set defaults where null (should not happen)
UPDATE app_limits SET
  max_stages_per_job = COALESCE(max_stages_per_job, 20),
  max_pipelines_per_stage = COALESCE(max_pipelines_per_stage, 20),
  max_steps_per_pipeline = COALESCE(max_steps_per_pipeline, 50)
WHERE owner_user_id IS NOT NULL;

-- Insert platform global row if missing
INSERT INTO app_limits (
  owner_user_id,
  max_stages_per_job,
  max_pipelines_per_stage,
  max_steps_per_pipeline,
  max_jobs_per_owner,
  max_triggers_per_owner,
  max_runs_per_utc_day,
  max_runs_per_utc_month
)
SELECT
  NULL,
  20,
  20,
  50,
  50,
  50,
  500,
  10000
WHERE NOT EXISTS (SELECT 1 FROM app_limits WHERE owner_user_id IS NULL);

-- ---------------------------------------------------------------------------
-- 2. New-user defaults (single row; seed only — not used in runtime resolution)
-- ---------------------------------------------------------------------------

CREATE TABLE app_limits_new_user_defaults (
  id int PRIMARY KEY CHECK (id = 1),
  max_stages_per_job int NOT NULL CHECK (max_stages_per_job > 0),
  max_pipelines_per_stage int NOT NULL CHECK (max_pipelines_per_stage > 0),
  max_steps_per_pipeline int NOT NULL CHECK (max_steps_per_pipeline > 0),
  max_jobs_per_owner int NOT NULL CHECK (max_jobs_per_owner > 0),
  max_triggers_per_owner int NOT NULL CHECK (max_triggers_per_owner > 0),
  max_runs_per_utc_day int NOT NULL CHECK (max_runs_per_utc_day > 0),
  max_runs_per_utc_month int NOT NULL CHECK (max_runs_per_utc_month > 0),
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO app_limits_new_user_defaults (
  id,
  max_stages_per_job,
  max_pipelines_per_stage,
  max_steps_per_pipeline,
  max_jobs_per_owner,
  max_triggers_per_owner,
  max_runs_per_utc_day,
  max_runs_per_utc_month
) VALUES (
  1,
  20,
  20,
  50,
  20,
  20,
  200,
  5000
)
ON CONFLICT (id) DO NOTHING;

ALTER TABLE app_limits_new_user_defaults ENABLE ROW LEVEL SECURITY;

CREATE POLICY app_limits_new_user_defaults_select ON app_limits_new_user_defaults
  FOR SELECT TO authenticated USING (true);

-- No user writes; backend service role bypasses RLS

-- ---------------------------------------------------------------------------
-- 3. job_runs: composite index for quota counts
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_job_runs_owner_created
  ON job_runs (owner_user_id, created_at);

-- ---------------------------------------------------------------------------
-- 4. Atomic enqueue: count + insert in one transaction (per run)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.enqueue_job_run_with_quota_check(
  p_owner_user_id uuid,
  p_run_id uuid,
  p_job_id text,
  p_trigger_id text,
  p_target_id text,
  p_trigger_payload jsonb,
  p_definition_snapshot_ref text,
  p_platform_job_id text,
  p_day_cap int,
  p_month_cap int
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  day_start timestamptz;
  month_start timestamptz;
  day_count int;
  month_count int;
BEGIN
  IF p_day_cap IS NULL OR p_month_cap IS NULL THEN
    RAISE EXCEPTION 'LIMITS_NOT_CONFIGURED'
      USING ERRCODE = 'P0001';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtext('enqueue_quota:' || p_owner_user_id::text));

  -- UTC calendar day / month boundaries (timestamptz)
  day_start := (date_trunc('day', timezone('utc', now()))) AT TIME ZONE 'UTC';
  month_start := (date_trunc('month', timezone('utc', now()))) AT TIME ZONE 'UTC';

  SELECT COUNT(*) INTO day_count
  FROM job_runs
  WHERE owner_user_id = p_owner_user_id
    AND created_at >= day_start
    AND created_at < day_start + interval '1 day';

  SELECT COUNT(*) INTO month_count
  FROM job_runs
  WHERE owner_user_id = p_owner_user_id
    AND created_at >= month_start
    AND created_at < month_start + interval '1 month';

  IF day_count + 1 > p_day_cap THEN
    RAISE EXCEPTION 'RUN_QUOTA_EXCEEDED|day|%s|%s', p_day_cap, day_count
      USING ERRCODE = 'P0001';
  END IF;

  IF month_count + 1 > p_month_cap THEN
    RAISE EXCEPTION 'RUN_QUOTA_EXCEEDED|month|%s|%s', p_month_cap, month_count
      USING ERRCODE = 'P0001';
  END IF;

  INSERT INTO job_runs (
    id,
    owner_user_id,
    job_id,
    trigger_id,
    target_id,
    status,
    trigger_payload,
    definition_snapshot_ref,
    platform_job_id,
    retry_count
  ) VALUES (
    p_run_id,
    p_owner_user_id,
    p_job_id,
    p_trigger_id,
    p_target_id,
    'pending',
    COALESCE(p_trigger_payload, '{}'::jsonb),
    p_definition_snapshot_ref,
    p_platform_job_id,
    0
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.enqueue_job_run_with_quota_check(
  uuid, uuid, text, text, text, jsonb, text, text, int, int
) TO service_role;
