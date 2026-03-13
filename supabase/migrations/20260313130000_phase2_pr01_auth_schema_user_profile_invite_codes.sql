-- p2_pr01: Auth Schema, User Profile, and Invite Codes
-- Enum, user_profiles, invitation_codes with uniqueness and claim-integrity constraints.

-- ---------------------------------------------------------------------------
-- 1. user_type enum
-- ---------------------------------------------------------------------------
CREATE TYPE user_type_enum AS ENUM ('ADMIN', 'STANDARD', 'BETA_TESTER');

-- ---------------------------------------------------------------------------
-- 2. invitation_codes: single-use invite codes with claim metadata
-- ---------------------------------------------------------------------------
CREATE TABLE invitation_codes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL,
  date_issued timestamptz NOT NULL DEFAULT now(),
  date_claimed timestamptz,
  issued_to text,
  platform_issued_on text,
  claimed boolean NOT NULL DEFAULT false,
  claimed_at timestamptz,
  user_type user_type_enum NOT NULL,
  claimed_by_user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT invitation_codes_code_unique UNIQUE (code),
  CONSTRAINT invitation_codes_code_length CHECK (char_length(code) = 20),
  CONSTRAINT invitation_codes_claim_integrity CHECK (
    (claimed = false AND date_claimed IS NULL AND claimed_at IS NULL AND claimed_by_user_id IS NULL)
    OR
    (claimed = true AND date_claimed IS NOT NULL AND claimed_at IS NOT NULL)
  )
);

CREATE INDEX idx_invitation_codes_code ON invitation_codes (code);
CREATE INDEX idx_invitation_codes_claimed ON invitation_codes (claimed);
CREATE INDEX idx_invitation_codes_user_type ON invitation_codes (user_type);

-- ---------------------------------------------------------------------------
-- 3. user_profiles: profile data keyed by Supabase Auth user id
-- ---------------------------------------------------------------------------
CREATE TABLE user_profiles (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  user_type user_type_enum NOT NULL,
  invitation_code_id uuid REFERENCES invitation_codes(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_profiles_user_type ON user_profiles (user_type);
