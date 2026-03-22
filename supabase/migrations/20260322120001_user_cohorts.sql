-- Beta: user_cohorts + cohort_id on invitations and profiles (admin-invitation-management-ui.md)
-- Idempotent: safe if objects already exist (e.g. local DB created before migration was recorded).
-- Version 20260322120001: distinct from 20260322120002_resource_limits (Supabase uses prefix as schema_migrations PK).

CREATE TABLE IF NOT EXISTS user_cohorts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key text NOT NULL,
  description text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT user_cohorts_key_unique UNIQUE (key)
);

CREATE INDEX IF NOT EXISTS idx_user_cohorts_key ON user_cohorts (key);

ALTER TABLE invitation_codes
  ADD COLUMN IF NOT EXISTS cohort_id uuid REFERENCES user_cohorts (id) ON DELETE SET NULL;

ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS cohort_id uuid REFERENCES user_cohorts (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_invitation_codes_cohort_id ON invitation_codes (cohort_id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_cohort_id ON user_profiles (cohort_id);
