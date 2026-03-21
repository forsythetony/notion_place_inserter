-- p5: Admin runtime theme — presets + active pointer (see p5_admin-runtime-theme-spec.md)

CREATE TABLE ui_theme_presets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  config jsonb NOT NULL,
  is_system boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by_user_id uuid REFERENCES auth.users (id) ON DELETE SET NULL
);

CREATE INDEX idx_ui_theme_presets_updated_at ON ui_theme_presets (updated_at DESC);

CREATE TABLE app_ui_theme_settings (
  id smallint PRIMARY KEY CHECK (id = 1),
  active_preset_id uuid REFERENCES ui_theme_presets (id) ON DELETE SET NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO app_ui_theme_settings (id) VALUES (1);

-- Seed system preset (Calm Graphite — aligned with notion_pipeliner_ui index.css)
INSERT INTO ui_theme_presets (id, name, config, is_system)
VALUES (
  'a0000001-0000-4000-8000-000000000001'::uuid,
  'Default (Calm Graphite)',
  '{
    "schemaVersion": 1,
    "tokens": {
      "color": {
        "primary": "#7AA2F7",
        "secondary": "#A9B3C3",
        "secondaryTint": "#6B7280",
        "surface": "#161A22",
        "text": "#E8EDF5"
      },
      "radius": {
        "buttonPrimary": "8px",
        "buttonSecondary": "6px"
      },
      "typography": {
        "fontFamilySans": "system-ui, Segoe UI, Roboto, sans-serif"
      },
      "graph": {
        "edgeStroke": "#2A3140"
      }
    }
  }'::jsonb,
  true
);

UPDATE app_ui_theme_settings
SET active_preset_id = 'a0000001-0000-4000-8000-000000000001'::uuid,
    updated_at = now()
WHERE id = 1;
