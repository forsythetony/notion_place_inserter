-- Beta waves (rollout tranche) + FKs on waitlist, invitations, profiles.
-- Seeded waves for admin dropdown; no CRUD UI in v1.

CREATE TABLE beta_waves (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key text NOT NULL,
  label text NOT NULL,
  description text,
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT beta_waves_key_unique UNIQUE (key)
);

CREATE INDEX idx_beta_waves_sort_order ON beta_waves (sort_order, key);

ALTER TABLE beta_waitlist_submissions
  ADD COLUMN beta_wave_id uuid REFERENCES beta_waves (id) ON DELETE SET NULL;

ALTER TABLE invitation_codes
  ADD COLUMN beta_wave_id uuid REFERENCES beta_waves (id) ON DELETE SET NULL;

ALTER TABLE user_profiles
  ADD COLUMN beta_wave_id uuid REFERENCES beta_waves (id) ON DELETE SET NULL;

CREATE INDEX idx_beta_waitlist_submissions_beta_wave_id
  ON beta_waitlist_submissions (beta_wave_id);
CREATE INDEX idx_invitation_codes_beta_wave_id ON invitation_codes (beta_wave_id);
CREATE INDEX idx_user_profiles_beta_wave_id ON user_profiles (beta_wave_id);

ALTER TABLE beta_waitlist_submissions
  DROP CONSTRAINT IF EXISTS beta_waitlist_submissions_status_check;

ALTER TABLE beta_waitlist_submissions
  ADD CONSTRAINT beta_waitlist_submissions_status_check CHECK (
    status IN (
      'PENDING_REVIEW',
      'SHORTLISTED',
      'INVITED',
      'DECLINED',
      'SPAM'
    )
  );

INSERT INTO beta_waves (key, label, description, sort_order)
VALUES
  ('WAVE_1', 'Wave 1 — closed alpha', 'First tranche', 10),
  ('WAVE_2', 'Wave 2 — expanded beta', 'Second tranche', 20),
  ('WAVE_3', 'Wave 3 — open beta', 'Third tranche', 30)
ON CONFLICT (key) DO NOTHING;
