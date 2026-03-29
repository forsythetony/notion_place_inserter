-- icon_search_misses: job_id and job_run_id hold runtime app identifiers (e.g. loc_..., job_...)
-- not only PostgreSQL uuid literals. Widen from uuid to text so miss logging does not fail on insert.

ALTER TABLE public.icon_search_misses
  ALTER COLUMN job_id TYPE text USING job_id::text,
  ALTER COLUMN job_run_id TYPE text USING job_run_id::text;
