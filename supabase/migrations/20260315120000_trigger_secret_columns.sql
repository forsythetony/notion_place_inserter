-- Trigger secret columns for per-trigger HTTP auth (Bearer secret).
-- Secrets are auto-generated and rotatable; users cannot set them.

ALTER TABLE trigger_definitions
  ADD COLUMN IF NOT EXISTS secret_value text,
  ADD COLUMN IF NOT EXISTS secret_last_rotated_at timestamptz;

-- Backfill existing triggers with a generated secret (~30 chars)
UPDATE trigger_definitions
SET
  secret_value = encode(gen_random_bytes(15), 'hex'),
  secret_last_rotated_at = now()
WHERE secret_value IS NULL;

ALTER TABLE trigger_definitions
  ALTER COLUMN secret_value SET NOT NULL;
