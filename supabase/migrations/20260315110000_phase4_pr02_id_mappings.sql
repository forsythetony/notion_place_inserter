-- p4_pr02: ID mapping registry for nested run IDs (stage_run, pipeline_run, step_run, usage_record).
-- Write-once lookup: source_id -> mapped_uuid so historical rows remain resolvable if mapper algorithm changes.

CREATE TABLE id_mappings (
  entity_type text NOT NULL,
  source_id text NOT NULL,
  mapped_uuid uuid NOT NULL,
  mapper_version text NOT NULL DEFAULT 'v1',
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (entity_type, source_id),
  CONSTRAINT uq_id_mappings_entity_uuid UNIQUE (entity_type, mapped_uuid)
);

CREATE INDEX idx_id_mappings_entity_type ON id_mappings (entity_type);
CREATE INDEX idx_id_mappings_mapped_uuid ON id_mappings (entity_type, mapped_uuid);

COMMENT ON TABLE id_mappings IS 'Registry for deterministic source_id->uuid mapping; never overwrite existing rows.';
