-- p4_pr01: Phase 4 Datastore Schema and Migrations
-- Product model tables for definitions and runs; RLS for owner-scoped isolation.
-- Domain classes and service interfaces unchanged; no runtime cutover yet.

-- ---------------------------------------------------------------------------
-- 1. Enums and check constraints
-- ---------------------------------------------------------------------------
CREATE TYPE entity_status_enum AS ENUM ('active', 'inactive', 'draft', 'archived');
CREATE TYPE visibility_enum AS ENUM ('platform', 'owner');
CREATE TYPE run_status_enum AS ENUM ('pending', 'running', 'succeeded', 'failed', 'cancelled');

-- ---------------------------------------------------------------------------
-- 2. Catalog tables (platform-owned, no owner_user_id)
-- ---------------------------------------------------------------------------

CREATE TABLE connector_templates (
  id text PRIMARY KEY,
  slug text NOT NULL,
  display_name text NOT NULL,
  connector_type text NOT NULL,
  provider text NOT NULL,
  auth_strategy text NOT NULL,
  capabilities jsonb NOT NULL DEFAULT '[]',
  config_schema jsonb NOT NULL DEFAULT '{}',
  secret_schema jsonb NOT NULL DEFAULT '{}',
  status entity_status_enum NOT NULL DEFAULT 'active',
  visibility visibility_enum NOT NULL DEFAULT 'platform',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_connector_templates_slug ON connector_templates (slug);

CREATE TABLE target_templates (
  id text PRIMARY KEY,
  slug text NOT NULL,
  display_name text NOT NULL,
  target_kind text NOT NULL,
  required_connector_template_id text NOT NULL REFERENCES connector_templates(id) ON DELETE RESTRICT,
  supports_schema_snapshots boolean NOT NULL DEFAULT true,
  property_types_supported jsonb NOT NULL DEFAULT '[]',
  status entity_status_enum NOT NULL DEFAULT 'active',
  visibility visibility_enum NOT NULL DEFAULT 'platform',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_target_templates_slug ON target_templates (slug);

CREATE TABLE step_templates (
  id text PRIMARY KEY,
  slug text NOT NULL,
  display_name text NOT NULL,
  step_kind text NOT NULL,
  description text NOT NULL DEFAULT '',
  input_contract jsonb NOT NULL DEFAULT '{}',
  output_contract jsonb NOT NULL DEFAULT '{}',
  config_schema jsonb NOT NULL DEFAULT '{}',
  runtime_binding text NOT NULL,
  category text NOT NULL DEFAULT 'general',
  status entity_status_enum NOT NULL DEFAULT 'active',
  visibility visibility_enum NOT NULL DEFAULT 'platform',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_step_templates_slug ON step_templates (slug);

-- ---------------------------------------------------------------------------
-- 3. Owner-scoped definition tables
-- ---------------------------------------------------------------------------

CREATE TABLE connector_instances (
  id text NOT NULL,
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  connector_template_id text NOT NULL REFERENCES connector_templates(id) ON DELETE RESTRICT,
  display_name text NOT NULL,
  status entity_status_enum NOT NULL DEFAULT 'active',
  config jsonb NOT NULL DEFAULT '{}',
  secret_ref text,
  last_validated_at timestamptz,
  last_error text,
  visibility visibility_enum NOT NULL DEFAULT 'owner',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id, owner_user_id)
);

CREATE INDEX idx_connector_instances_owner ON connector_instances (owner_user_id);
CREATE INDEX idx_connector_instances_template ON connector_instances (connector_template_id);

CREATE TABLE data_targets (
  id text NOT NULL,
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  target_template_id text NOT NULL REFERENCES target_templates(id) ON DELETE RESTRICT,
  connector_instance_id text NOT NULL,
  display_name text NOT NULL,
  external_target_id text NOT NULL,
  status entity_status_enum NOT NULL DEFAULT 'active',
  active_schema_snapshot_id text,
  target_settings jsonb,
  property_rules jsonb,
  visibility visibility_enum NOT NULL DEFAULT 'owner',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id, owner_user_id),
  CONSTRAINT fk_connector_instance FOREIGN KEY (connector_instance_id, owner_user_id)
    REFERENCES connector_instances(id, owner_user_id) ON DELETE RESTRICT
);

CREATE INDEX idx_data_targets_owner ON data_targets (owner_user_id);
CREATE INDEX idx_data_targets_template ON data_targets (target_template_id);

CREATE TABLE target_schema_snapshots (
  id text NOT NULL,
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  data_target_id text NOT NULL,
  version text NOT NULL,
  fetched_at timestamptz NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  source_connector_instance_id text NOT NULL,
  properties jsonb NOT NULL DEFAULT '[]',
  raw_source_payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id, owner_user_id),
  CONSTRAINT fk_data_target FOREIGN KEY (data_target_id, owner_user_id)
    REFERENCES data_targets(id, owner_user_id) ON DELETE CASCADE
);

CREATE INDEX idx_target_schema_snapshots_owner ON target_schema_snapshots (owner_user_id);
CREATE INDEX idx_target_schema_snapshots_target ON target_schema_snapshots (data_target_id, owner_user_id);
CREATE INDEX idx_target_schema_snapshots_active ON target_schema_snapshots (data_target_id, owner_user_id) WHERE is_active = true;

-- Job definitions (created before trigger_definitions due to FK)
CREATE TABLE job_definitions (
  id text NOT NULL,
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name text NOT NULL,
  trigger_id text NOT NULL,
  target_id text NOT NULL,
  status entity_status_enum NOT NULL DEFAULT 'active',
  stage_ids jsonb NOT NULL DEFAULT '[]',
  default_run_settings jsonb,
  visibility visibility_enum NOT NULL DEFAULT 'owner',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id, owner_user_id),
  CONSTRAINT fk_target FOREIGN KEY (target_id, owner_user_id)
    REFERENCES data_targets(id, owner_user_id) ON DELETE RESTRICT
);

CREATE INDEX idx_job_definitions_owner ON job_definitions (owner_user_id);
CREATE INDEX idx_job_definitions_trigger ON job_definitions (trigger_id, owner_user_id);

-- Trigger definitions (Phase 1 http_triggers is a minimal stub; Phase 4 uses full product model)
CREATE TABLE trigger_definitions (
  id text NOT NULL,
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  trigger_type text NOT NULL DEFAULT 'http',
  display_name text NOT NULL,
  path text NOT NULL,
  method text NOT NULL DEFAULT 'POST',
  request_body_schema jsonb NOT NULL DEFAULT '{}',
  status entity_status_enum NOT NULL DEFAULT 'active',
  job_id text NOT NULL,
  auth_mode text NOT NULL DEFAULT 'bearer',
  visibility visibility_enum NOT NULL DEFAULT 'owner',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id, owner_user_id),
  CONSTRAINT uq_trigger_path_per_owner UNIQUE (owner_user_id, path),
  CONSTRAINT fk_job FOREIGN KEY (job_id, owner_user_id)
    REFERENCES job_definitions(id, owner_user_id) ON DELETE RESTRICT
);

CREATE INDEX idx_trigger_definitions_owner ON trigger_definitions (owner_user_id);
CREATE INDEX idx_trigger_definitions_path ON trigger_definitions (owner_user_id, path);

-- Add FK for data_targets.active_schema_snapshot_id (deferred to resolve circular ref)
ALTER TABLE data_targets
  ADD CONSTRAINT fk_active_schema FOREIGN KEY (active_schema_snapshot_id, owner_user_id)
  REFERENCES target_schema_snapshots(id, owner_user_id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE stage_definitions (
  id text NOT NULL,
  job_id text NOT NULL,
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name text NOT NULL,
  sequence int NOT NULL CHECK (sequence >= 0),
  pipeline_ids jsonb NOT NULL DEFAULT '[]',
  pipeline_run_mode text NOT NULL DEFAULT 'parallel',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id, owner_user_id),
  CONSTRAINT fk_stage_job FOREIGN KEY (job_id, owner_user_id)
    REFERENCES job_definitions(id, owner_user_id) ON DELETE CASCADE,
  CONSTRAINT uq_stage_sequence_per_job UNIQUE (job_id, owner_user_id, sequence)
);

CREATE INDEX idx_stage_definitions_job ON stage_definitions (job_id, owner_user_id);

CREATE TABLE pipeline_definitions (
  id text NOT NULL,
  stage_id text NOT NULL,
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name text NOT NULL,
  sequence int NOT NULL CHECK (sequence >= 0),
  step_ids jsonb NOT NULL DEFAULT '[]',
  purpose text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id, owner_user_id),
  CONSTRAINT fk_pipeline_stage FOREIGN KEY (stage_id, owner_user_id)
    REFERENCES stage_definitions(id, owner_user_id) ON DELETE CASCADE,
  CONSTRAINT uq_pipeline_sequence_per_stage UNIQUE (stage_id, owner_user_id, sequence)
);

CREATE INDEX idx_pipeline_definitions_stage ON pipeline_definitions (stage_id, owner_user_id);

CREATE TABLE step_instances (
  id text NOT NULL,
  pipeline_id text NOT NULL,
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  step_template_id text NOT NULL REFERENCES step_templates(id) ON DELETE RESTRICT,
  display_name text NOT NULL,
  sequence int NOT NULL CHECK (sequence >= 0),
  input_bindings jsonb NOT NULL DEFAULT '{}',
  config jsonb NOT NULL DEFAULT '{}',
  failure_policy text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id, owner_user_id),
  CONSTRAINT fk_step_pipeline FOREIGN KEY (pipeline_id, owner_user_id)
    REFERENCES pipeline_definitions(id, owner_user_id) ON DELETE CASCADE,
  CONSTRAINT uq_step_sequence_per_pipeline UNIQUE (pipeline_id, owner_user_id, sequence)
);

CREATE INDEX idx_step_instances_pipeline ON step_instances (pipeline_id, owner_user_id);
CREATE INDEX idx_step_instances_template ON step_instances (step_template_id);

-- ---------------------------------------------------------------------------
-- 4. Run and usage tables
-- ---------------------------------------------------------------------------

CREATE TABLE job_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  job_id text NOT NULL,
  trigger_id text NOT NULL,
  target_id text NOT NULL,
  status run_status_enum NOT NULL DEFAULT 'pending',
  trigger_payload jsonb NOT NULL DEFAULT '{}',
  definition_snapshot_ref text,
  platform_job_id text,
  retry_count int NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
  started_at timestamptz,
  completed_at timestamptz,
  error_summary text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_job_runs_owner ON job_runs (owner_user_id);
CREATE INDEX idx_job_runs_job ON job_runs (owner_user_id, job_id);
CREATE INDEX idx_job_runs_platform_job ON job_runs (platform_job_id) WHERE platform_job_id IS NOT NULL;
CREATE INDEX idx_job_runs_status ON job_runs (status);
CREATE INDEX idx_job_runs_created ON job_runs (created_at DESC);

CREATE TABLE stage_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_run_id uuid NOT NULL REFERENCES job_runs(id) ON DELETE CASCADE,
  stage_id text NOT NULL,
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  status run_status_enum NOT NULL DEFAULT 'pending',
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_stage_runs_job_run ON stage_runs (job_run_id);
CREATE INDEX idx_stage_runs_owner ON stage_runs (owner_user_id);

CREATE TABLE pipeline_run_executions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stage_run_id uuid NOT NULL REFERENCES stage_runs(id) ON DELETE CASCADE,
  pipeline_id text NOT NULL,
  job_run_id uuid NOT NULL REFERENCES job_runs(id) ON DELETE CASCADE,
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  status run_status_enum NOT NULL DEFAULT 'pending',
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_pipeline_run_executions_stage ON pipeline_run_executions (stage_run_id);
CREATE INDEX idx_pipeline_run_executions_job_run ON pipeline_run_executions (job_run_id);
CREATE INDEX idx_pipeline_run_executions_owner ON pipeline_run_executions (owner_user_id);

CREATE TABLE step_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline_run_id uuid NOT NULL REFERENCES pipeline_run_executions(id) ON DELETE CASCADE,
  step_id text NOT NULL,
  step_template_id text NOT NULL,
  job_run_id uuid NOT NULL REFERENCES job_runs(id) ON DELETE CASCADE,
  stage_run_id uuid NOT NULL REFERENCES stage_runs(id) ON DELETE CASCADE,
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  status run_status_enum NOT NULL DEFAULT 'pending',
  input_summary jsonb,
  output_summary jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  error_summary text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_step_runs_pipeline_run ON step_runs (pipeline_run_id);
CREATE INDEX idx_step_runs_job_run ON step_runs (job_run_id);
CREATE INDEX idx_step_runs_owner ON step_runs (owner_user_id);

CREATE TABLE usage_records (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_run_id uuid NOT NULL REFERENCES job_runs(id) ON DELETE CASCADE,
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  usage_type text NOT NULL,
  provider text NOT NULL,
  metric_name text NOT NULL,
  metric_value numeric NOT NULL CHECK (metric_value >= 0),
  step_run_id uuid REFERENCES step_runs(id) ON DELETE SET NULL,
  metadata jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_usage_records_job_run ON usage_records (job_run_id);
CREATE INDEX idx_usage_records_owner ON usage_records (owner_user_id);
CREATE INDEX idx_usage_records_type ON usage_records (usage_type);

-- ---------------------------------------------------------------------------
-- 5. App limits (owner-scoped or global when owner_user_id is null)
-- ---------------------------------------------------------------------------

CREATE TABLE app_limits (
  owner_user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
  max_stages_per_job int NOT NULL CHECK (max_stages_per_job > 0),
  max_pipelines_per_stage int NOT NULL CHECK (max_pipelines_per_stage > 0),
  max_steps_per_pipeline int NOT NULL CHECK (max_steps_per_pipeline > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_user_id)
);

-- Single global default row (owner_user_id NULL = platform default)
CREATE UNIQUE INDEX idx_app_limits_global ON app_limits ((true)) WHERE owner_user_id IS NULL;

-- ---------------------------------------------------------------------------
-- 6. RLS: Enable and policies for owner-scoped tables
-- ---------------------------------------------------------------------------

ALTER TABLE connector_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_targets ENABLE ROW LEVEL SECURITY;
ALTER TABLE target_schema_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE trigger_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE stage_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE step_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE stage_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_run_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE step_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_limits ENABLE ROW LEVEL SECURITY;

-- Catalog tables: public read for authenticated users; write via service role only
ALTER TABLE connector_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE target_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE step_templates ENABLE ROW LEVEL SECURITY;

-- Owner-scoped: restrict to own rows
CREATE POLICY connector_instances_owner ON connector_instances
  FOR ALL USING (owner_user_id = auth.uid());

CREATE POLICY data_targets_owner ON data_targets
  FOR ALL USING (owner_user_id = auth.uid());

CREATE POLICY target_schema_snapshots_owner ON target_schema_snapshots
  FOR ALL USING (owner_user_id = auth.uid());

CREATE POLICY trigger_definitions_owner ON trigger_definitions
  FOR ALL USING (owner_user_id = auth.uid());

CREATE POLICY job_definitions_owner ON job_definitions
  FOR ALL USING (owner_user_id = auth.uid());

CREATE POLICY stage_definitions_owner ON stage_definitions
  FOR ALL USING (owner_user_id = auth.uid());

CREATE POLICY pipeline_definitions_owner ON pipeline_definitions
  FOR ALL USING (owner_user_id = auth.uid());

CREATE POLICY step_instances_owner ON step_instances
  FOR ALL USING (owner_user_id = auth.uid());

CREATE POLICY job_runs_owner ON job_runs
  FOR ALL USING (owner_user_id = auth.uid());

CREATE POLICY stage_runs_owner ON stage_runs
  FOR ALL USING (owner_user_id = auth.uid());

CREATE POLICY pipeline_run_executions_owner ON pipeline_run_executions
  FOR ALL USING (owner_user_id = auth.uid());

CREATE POLICY step_runs_owner ON step_runs
  FOR ALL USING (owner_user_id = auth.uid());

CREATE POLICY usage_records_owner ON usage_records
  FOR ALL USING (owner_user_id = auth.uid());

CREATE POLICY app_limits_select ON app_limits
  FOR SELECT USING (owner_user_id = auth.uid() OR owner_user_id IS NULL);
CREATE POLICY app_limits_modify ON app_limits
  FOR ALL USING (owner_user_id = auth.uid());

-- Catalog: allow authenticated read; no direct user write (service role bypasses RLS)
CREATE POLICY connector_templates_read ON connector_templates
  FOR SELECT TO authenticated USING (true);

CREATE POLICY target_templates_read ON target_templates
  FOR SELECT TO authenticated USING (true);

CREATE POLICY step_templates_read ON step_templates
  FOR SELECT TO authenticated USING (true);
