-- Allow triggers to exist without a linked job (for create-trigger-then-assign-to-pipeline flow).
-- FK remains: when job_id is set, it must reference a valid job; NULL is allowed.
ALTER TABLE trigger_definitions
  ALTER COLUMN job_id DROP NOT NULL;
