-- Fix PostgREST upsert on app_limits: ON CONFLICT (owner_user_id) requires a non-partial unique
-- index on that column. Partial indexes idx_app_limits_one_owner / idx_app_limits_one_global
-- do not satisfy ON CONFLICT (42P10). Replace with one UNIQUE index (NULLS NOT DISTINCT, PG15+).
-- Safe for DBs that already applied 20260322120002 with partial indexes, or fresh installs that
-- already have idx_app_limits_owner_user_id_unique from the updated 20260322120002.

DROP INDEX IF EXISTS idx_app_limits_one_owner;
DROP INDEX IF EXISTS idx_app_limits_one_global;

-- Deduplicate if bad data exists (should be rare)
DELETE FROM app_limits a
  USING app_limits b
  WHERE a.owner_user_id IS NOT NULL
    AND a.owner_user_id = b.owner_user_id
    AND a.id > b.id;

DELETE FROM app_limits a
  WHERE a.owner_user_id IS NULL
    AND EXISTS (
      SELECT 1 FROM app_limits b
      WHERE b.owner_user_id IS NULL AND b.id < a.id
    );

CREATE UNIQUE INDEX IF NOT EXISTS idx_app_limits_owner_user_id_unique
  ON app_limits (owner_user_id)
  NULLS NOT DISTINCT;
