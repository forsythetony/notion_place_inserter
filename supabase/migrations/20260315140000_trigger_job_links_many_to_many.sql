-- Many-to-many trigger-job linkage. Replaces trigger_definitions.job_id and job_definitions.trigger_id.

-- 1. Create link table
CREATE TABLE trigger_job_links (
  trigger_id text NOT NULL,
  job_id text NOT NULL,
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (trigger_id, job_id, owner_user_id),
  CONSTRAINT fk_trigger_link FOREIGN KEY (trigger_id, owner_user_id)
    REFERENCES trigger_definitions(id, owner_user_id) ON DELETE CASCADE,
  CONSTRAINT fk_job_link FOREIGN KEY (job_id, owner_user_id)
    REFERENCES job_definitions(id, owner_user_id) ON DELETE CASCADE
);

CREATE INDEX idx_trigger_job_links_trigger ON trigger_job_links (trigger_id, owner_user_id);
CREATE INDEX idx_trigger_job_links_job ON trigger_job_links (job_id, owner_user_id);

-- 2. Backfill from trigger_definitions.job_id (where not null)
INSERT INTO trigger_job_links (trigger_id, job_id, owner_user_id)
SELECT id, job_id, owner_user_id
FROM trigger_definitions
WHERE job_id IS NOT NULL
ON CONFLICT (trigger_id, job_id, owner_user_id) DO NOTHING;

-- 3. Backfill from job_definitions.trigger_id (may add links not in trigger_definitions)
INSERT INTO trigger_job_links (trigger_id, job_id, owner_user_id)
SELECT trigger_id, id, owner_user_id
FROM job_definitions
ON CONFLICT (trigger_id, job_id, owner_user_id) DO NOTHING;

-- 4. Drop legacy linkage: trigger_definitions.job_id
ALTER TABLE trigger_definitions DROP CONSTRAINT IF EXISTS fk_job;
ALTER TABLE trigger_definitions DROP COLUMN IF EXISTS job_id;

-- 5. Drop legacy linkage: job_definitions.trigger_id
DROP INDEX IF EXISTS idx_job_definitions_trigger;
ALTER TABLE job_definitions DROP COLUMN IF EXISTS trigger_id;

-- 6. RLS for trigger_job_links
ALTER TABLE trigger_job_links ENABLE ROW LEVEL SECURITY;
CREATE POLICY trigger_job_links_owner ON trigger_job_links
  FOR ALL USING (owner_user_id = auth.uid());
