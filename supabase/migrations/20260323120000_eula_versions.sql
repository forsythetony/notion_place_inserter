-- EULA versions (draft / published / archived), profile acceptance linkage, and atomic publish RPC.

-- ---------------------------------------------------------------------------
-- 1. Enum and table
-- ---------------------------------------------------------------------------
CREATE TYPE eula_version_status AS ENUM ('draft', 'published', 'archived');

CREATE TABLE eula_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status eula_version_status NOT NULL,
  version_label text NOT NULL,
  full_text text NOT NULL,
  content_sha256 text NOT NULL,
  plain_language_summary jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz,
  created_by_user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  CONSTRAINT eula_versions_version_label_unique UNIQUE (version_label),
  CONSTRAINT eula_versions_content_sha256_hex CHECK (char_length(content_sha256) = 64)
);

CREATE UNIQUE INDEX eula_versions_one_published ON eula_versions ((1)) WHERE status = 'published';

CREATE INDEX idx_eula_versions_status ON eula_versions (status);
CREATE INDEX idx_eula_versions_created_at ON eula_versions (created_at DESC);

COMMENT ON TABLE eula_versions IS 'End-user license agreement versions; at most one published row.';
COMMENT ON COLUMN eula_versions.content_sha256 IS 'Hex SHA-256 of full_text UTF-8 bytes; computed by API on write.';

-- ---------------------------------------------------------------------------
-- 2. user_profiles acceptance (nullable for legacy / non-signup paths)
-- ---------------------------------------------------------------------------
ALTER TABLE user_profiles
  ADD COLUMN eula_version_id uuid REFERENCES eula_versions(id) ON DELETE SET NULL,
  ADD COLUMN eula_accepted_at timestamptz;

CREATE INDEX idx_user_profiles_eula_version_id ON user_profiles (eula_version_id);

COMMENT ON COLUMN user_profiles.eula_version_id IS 'EULA version attested at signup; NULL for legacy or admin-provisioned profiles.';
COMMENT ON COLUMN user_profiles.eula_accepted_at IS 'UTC time when eula_version_id was accepted; NULL when eula_version_id is NULL.';

-- ---------------------------------------------------------------------------
-- 3. Publish draft in one transaction (archive current published, publish draft)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.publish_eula_version(draft_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM eula_versions WHERE id = draft_id AND status = 'draft'
  ) THEN
    RAISE EXCEPTION 'publish_eula_version: row % is not a draft or does not exist', draft_id;
  END IF;

  UPDATE eula_versions
  SET status = 'archived',
      updated_at = now()
  WHERE status = 'published';

  UPDATE eula_versions
  SET status = 'published',
      published_at = now(),
      updated_at = now()
  WHERE id = draft_id;
END;
$$;

GRANT EXECUTE ON FUNCTION public.publish_eula_version(uuid) TO service_role;

-- ---------------------------------------------------------------------------
-- 4. RLS: direct client access not intended; service_role bypasses RLS
-- ---------------------------------------------------------------------------
ALTER TABLE eula_versions ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 5. Seed one published EULA (aligned with public Terms of Use narrative)
-- ---------------------------------------------------------------------------
WITH seed AS (
  SELECT $seed$
END USER LICENSE AGREEMENT — Flow Pipeliner (Beta)

Last updated: March 2026. These terms govern your use of Flow Pipeliner and the Flow Pipeliner Notion integration provided by Lucid Path Solutions.

1. Acceptance
By connecting your Notion workspace to Flow Pipeliner or otherwise using our integration, you agree to this End User License Agreement. If you do not agree, do not use the integration.

2. Description of Service
Flow Pipeliner is a Notion integration that enables pipeline automation and data sync between your Notion workspace and other systems you configure. The service is provided by Lucid Path Solutions and operates in accordance with Notion's API terms and policies.

3. Acceptable Use
You agree to use Flow Pipeliner only for lawful purposes. You will not: violate applicable laws or regulations; infringe intellectual property or privacy rights of others; transmit malware, spam, or harmful content; circumvent security measures or abuse the Notion API; or resell or redistribute the service without authorization. We may suspend or terminate access if we reasonably believe you have violated these terms.

4. Data and Privacy
Our collection and use of data is described in our Privacy Policy. By using Flow Pipeliner, you consent to that policy.

5. Disclaimers
Flow Pipeliner is provided "as is" and "as available." We do not warrant uninterrupted, error-free, or secure operation. We are not responsible for data loss, downtime, or consequences arising from your use of the integration or third-party services (including Notion).

6. Limitation of Liability
To the maximum extent permitted by law, Lucid Path Solutions and its affiliates shall not be liable for indirect, incidental, special, consequential, or punitive damages, or for loss of data, profits, or business opportunities arising from your use of Flow Pipeliner.

7. Changes
We may update these terms. Continued use after changes constitutes acceptance. We will use reasonable means to notify you of material changes.

8. Contact
For questions, contact Lucid Path Solutions at legal@lucidpathsolutions.com.
$seed$::text AS full_text
)
INSERT INTO eula_versions (
  status,
  version_label,
  full_text,
  content_sha256,
  plain_language_summary,
  published_at,
  updated_at
)
SELECT
  'published',
  '1.0.0-beta',
  s.full_text,
  encode(sha256(convert_to(s.full_text, 'UTF8')), 'hex'),
  jsonb_build_object(
    'dos',
    jsonb_build_array(
      'Use Flow Pipeliner in compliance with applicable laws and Notion policies.',
      'Review the Privacy Policy to understand how we handle data.'
    ),
    'donts',
    jsonb_build_array(
      'Do not use the service to violate others'' rights or to transmit harmful content.',
      'Do not attempt to circumvent security or abuse APIs.'
    ),
    'cautions',
    jsonb_build_array(
      'The beta is provided as-is; we are not liable for lost revenue or indirect damages to the extent permitted by law.'
    )
  ),
  now(),
  now()
FROM seed s;
