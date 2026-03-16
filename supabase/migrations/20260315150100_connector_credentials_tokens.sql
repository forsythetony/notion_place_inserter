-- Store OAuth tokens in connector_credentials.
-- When CREDENTIAL_ENCRYPTION_KEY is set, payload is encrypted at rest.
-- secret_ref remains a pointer; token_payload holds the actual tokens (or encrypted blob).

ALTER TABLE connector_credentials
  ADD COLUMN IF NOT EXISTS token_payload jsonb;

COMMENT ON COLUMN connector_credentials.token_payload IS
  'OAuth token payload: access_token, refresh_token, workspace_id, etc. Encrypted when CREDENTIAL_ENCRYPTION_KEY is set.';
