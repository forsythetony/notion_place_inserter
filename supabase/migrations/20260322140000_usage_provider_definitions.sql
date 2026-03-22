-- Usage provider registry: human-readable labels for usage_records.provider strings.
-- Seeded from product_model/catalog/usage_providers.yaml on bootstrap.

CREATE TABLE IF NOT EXISTS usage_provider_definitions (
  provider_id text PRIMARY KEY,
  display_name text NOT NULL,
  description text NOT NULL DEFAULT '',
  billing_unit text NOT NULL DEFAULT 'call',
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_usage_provider_definitions_display
  ON usage_provider_definitions (display_name);

COMMENT ON TABLE usage_provider_definitions IS
  'Operator-facing metadata for usage_records.provider; YAML-seeded, optional admin edits.';
