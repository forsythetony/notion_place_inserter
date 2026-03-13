-- Public RPC wrappers for pgmq (send, read, archive).
-- Keeps pgmq schema unexposed; PostgREST only needs public schema.
-- SECURITY DEFINER runs with definer privileges; search_path hardened.

-- ---------------------------------------------------------------------------
-- 1. pgmq_send: enqueue a message with optional delay
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.pgmq_send(
  queue_name text,
  msg jsonb,
  delay int DEFAULT 0
)
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
SET search_path = public, pgmq
AS $$
  SELECT (SELECT * FROM pgmq.send(queue_name, msg, delay) LIMIT 1);
$$;

-- ---------------------------------------------------------------------------
-- 2. pgmq_read: read messages with visibility timeout
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.pgmq_read(
  queue_name text,
  vt int,
  qty int
)
RETURNS TABLE(msg_id bigint, read_ct integer, enqueued_at timestamptz, message jsonb)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public, pgmq
AS $$
  SELECT m.msg_id, m.read_ct, m.enqueued_at, m.message
  FROM pgmq.read(queue_name, vt, qty) m;
$$;

-- ---------------------------------------------------------------------------
-- 3. pgmq_archive: archive a message by id
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.pgmq_archive(
  queue_name text,
  msg_id bigint
)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
SET search_path = public, pgmq
AS $$
  SELECT pgmq.archive(queue_name, msg_id);
$$;

-- ---------------------------------------------------------------------------
-- 4. Grant execute to service_role (backend uses secret key)
-- ---------------------------------------------------------------------------
GRANT EXECUTE ON FUNCTION public.pgmq_send(text, jsonb, int) TO service_role;
GRANT EXECUTE ON FUNCTION public.pgmq_read(text, int, int) TO service_role;
GRANT EXECUTE ON FUNCTION public.pgmq_archive(text, bigint) TO service_role;
