-- Public beta waitlist submissions (pre-auth marketing intake).
-- RLS enabled; writes via service role / backend only (no anon policies).

CREATE TABLE beta_waitlist_submissions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL,
  email_normalized text NOT NULL,
  name text NOT NULL,
  heard_about text NOT NULL,
  heard_about_other text,
  work_role text NOT NULL,
  notion_use_case text NOT NULL,
  status text NOT NULL DEFAULT 'PENDING_REVIEW',
  submission_source text NOT NULL DEFAULT 'landing_page_waitlist',
  submission_count integer NOT NULL DEFAULT 1,
  first_submitted_at timestamptz NOT NULL DEFAULT now(),
  last_submitted_at timestamptz NOT NULL DEFAULT now(),
  captcha_provider text,
  captcha_verified_at timestamptz,
  client_ip_hash text,
  user_agent text,
  referrer text,
  invitation_code_id uuid REFERENCES invitation_codes(id) ON DELETE SET NULL,
  invited_at timestamptz,
  reviewed_at timestamptz,
  admin_notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT beta_waitlist_submissions_email_normalized_unique UNIQUE (email_normalized),
  CONSTRAINT beta_waitlist_submissions_submission_count_positive CHECK (submission_count >= 1)
);

CREATE INDEX idx_beta_waitlist_submissions_last_submitted_at
  ON beta_waitlist_submissions (last_submitted_at DESC);
CREATE INDEX idx_beta_waitlist_submissions_status ON beta_waitlist_submissions (status);

ALTER TABLE beta_waitlist_submissions ENABLE ROW LEVEL SECURITY;
