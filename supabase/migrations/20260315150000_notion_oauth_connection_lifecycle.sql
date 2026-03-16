-- Notion OAuth connection lifecycle: state, credentials, external sources.
-- Enables disconnect/reconnect and database discovery/selection flows.

-- ---------------------------------------------------------------------------
-- 1. Extend connector_instances for connection lifecycle
-- ---------------------------------------------------------------------------
ALTER TABLE connector_instances
  ADD COLUMN IF NOT EXISTS auth_status text NOT NULL DEFAULT 'pending'
    CHECK (auth_status IN ('pending', 'connected', 'token_expired', 'revoked', 'error')),
  ADD COLUMN IF NOT EXISTS authorized_at timestamptz,
  ADD COLUMN IF NOT EXISTS disconnected_at timestamptz,
  ADD COLUMN IF NOT EXISTS provider_account_id text,
  ADD COLUMN IF NOT EXISTS provider_account_name text,
  ADD COLUMN IF NOT EXISTS last_synced_at timestamptz,
  ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_connector_instances_auth_status
  ON connector_instances (owner_user_id, auth_status);

-- ---------------------------------------------------------------------------
-- 2. OAuth flow state (anti-replay, expiry)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oauth_connection_states (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  provider text NOT NULL,
  state_token_hash text NOT NULL,
  pkce_verifier_encrypted text,
  redirect_uri text NOT NULL,
  expires_at timestamptz NOT NULL,
  consumed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_oauth_connection_states_state_hash
  ON oauth_connection_states (state_token_hash);
CREATE INDEX idx_oauth_connection_states_owner
  ON oauth_connection_states (owner_user_id);
CREATE INDEX idx_oauth_connection_states_expires
  ON oauth_connection_states (expires_at) WHERE consumed_at IS NULL;

ALTER TABLE oauth_connection_states ENABLE ROW LEVEL SECURITY;
CREATE POLICY oauth_connection_states_owner ON oauth_connection_states
  FOR ALL USING (owner_user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- 3. Connector credentials (token lifecycle)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS connector_credentials (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  connector_instance_id text NOT NULL,
  provider text NOT NULL,
  credential_type text NOT NULL DEFAULT 'oauth2',
  secret_ref text NOT NULL,
  token_expires_at timestamptz,
  last_refreshed_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (owner_user_id, connector_instance_id, provider, credential_type),
  CONSTRAINT fk_connector_credential_instance
    FOREIGN KEY (connector_instance_id, owner_user_id)
    REFERENCES connector_instances(id, owner_user_id) ON DELETE CASCADE
);

CREATE INDEX idx_connector_credentials_owner
  ON connector_credentials (owner_user_id);
CREATE INDEX idx_connector_credentials_instance
  ON connector_credentials (connector_instance_id, owner_user_id);

ALTER TABLE connector_credentials ENABLE ROW LEVEL SECURITY;
CREATE POLICY connector_credentials_owner ON connector_credentials
  FOR ALL USING (owner_user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- 4. Discovered external sources (Notion data sources cache)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS connector_external_sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  connector_instance_id text NOT NULL,
  provider text NOT NULL,
  external_source_id text NOT NULL,
  external_parent_id text,
  display_name text NOT NULL,
  is_accessible boolean NOT NULL DEFAULT true,
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  last_sync_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (owner_user_id, connector_instance_id, external_source_id),
  CONSTRAINT fk_external_source_connector
    FOREIGN KEY (connector_instance_id, owner_user_id)
    REFERENCES connector_instances(id, owner_user_id) ON DELETE CASCADE
);

CREATE INDEX idx_connector_external_sources_owner
  ON connector_external_sources (owner_user_id);
CREATE INDEX idx_connector_external_sources_instance
  ON connector_external_sources (connector_instance_id, owner_user_id);

ALTER TABLE connector_external_sources ENABLE ROW LEVEL SECURITY;
CREATE POLICY connector_external_sources_owner ON connector_external_sources
  FOR ALL USING (owner_user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- 5. Index for data_targets by connector (source selection queries)
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_data_targets_connector
  ON data_targets (owner_user_id, connector_instance_id);
