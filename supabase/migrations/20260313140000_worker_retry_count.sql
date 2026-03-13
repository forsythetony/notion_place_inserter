-- Worker retry: add retry_count to platform_jobs for bounded retry tracking.
-- Enables worker to persist retry attempts and fail fast after final attempt.

ALTER TABLE platform_jobs
  ADD COLUMN IF NOT EXISTS retry_count integer NOT NULL DEFAULT 0;

COMMENT ON COLUMN platform_jobs.retry_count IS 'Number of retries consumed for this job (0 = first attempt, 1+ = retries).';
