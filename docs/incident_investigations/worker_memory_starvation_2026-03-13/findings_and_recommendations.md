# Worker Memory Starvation Investigation (2026-03-13)

## Scope

- Service: `notion-pipeliner-worker` (Render)
- Signals reviewed:
  - Render memory chart screenshot (512 MB limit)
  - Runtime logs in `logs.txt` (original + appended logs)

## Executive Finding (Updated)

The original primary hypothesis still stands: repeated poison-message processing is likely a major contributor.  
However, the new logs show we still need better runtime visibility to confirm *where* memory grows between restarts.

Confidence: **medium** (strong operational pattern, limited heap-level telemetry).

## What New Logs Add

1. **Restarts continue after initial mitigation work**
   - New startup sequence appears again at `22:05` and `22:15` (`==> Running 'python -m app.worker_main'`).
   - This confirms the process recycle pattern remains active.

2. **Worker retry delays are now explicitly logged**
   - `worker_starting | poll_interval=1.0 vt_seconds=300 retry_delays=(5, 30, 60)` appears in new logs.
   - This means retry backoff config is in effect in code path, but does not by itself prove poison jobs are being permanently removed.

3. **Environment still shows queue/table names unset**
   - `SUPABASE_QUEUE_NAME=[unset]`
   - `SUPABASE_TABLE_PLATFORM_JOBS=[unset]`
   - `SUPABASE_TABLE_PIPELINE_RUNS=[unset]`
   - `SUPABASE_TABLE_PIPELINE_RUN_EVENTS=[unset]`
   - If defaults are expected, this may be fine; if not, it can obscure control over retry/dead-letter behavior.

4. **Earlier deterministic FK failures remain a key signal**
   - Same `run_id` values repeatedly failed with `23503` FK violations.
   - This remains consistent with poison-message behavior and repeated reprocessing.

## Current Root Cause Hypotheses (Ranked)

1. **Poison message loop is still present for some failure classes**
   - Deterministic data-integrity errors (`pipeline_runs` parent missing) should converge quickly to terminal state.
   - If retries continue without archival/dead-letter, memory and log pressure accumulate.

2. **Memory pressure during repeated exception/retry path**
   - Large payloads, exception objects, or response blobs might be retained across loop iterations longer than expected.
   - Restart cadence can hide this until process reaches container limit.

3. **Insufficient observability hides true growth source**
   - We currently see startup/error logs, but not per-iteration memory deltas, queue depth by state, or object/heap growth categories.

## Additional Diagnostics To Add (High Priority)

### A) Process memory heartbeat logging

Add a periodic structured log every 30-60s in worker loop:
- `rss_mb`, `vms_mb`, `python_heap_mb` (if available)
- `gc_counts` (`gc.get_count()`)
- `open_fds` (if available)
- `queue_depth_visible`, `queue_depth_inflight`, `dead_letter_depth` (if available)
- `active_run_id` / `active_msg_id` (if processing)

Goal: correlate memory slope with queue state and retry activity.

### B) Per-message memory delta logging

Log at message boundaries:
- `mem_before_mb`, `mem_after_mb`, `mem_delta_mb`
- `msg_id`, `run_id`, `job_id`, `attempt`, `result` (`success`, `retry`, `failed_terminal`)
- `error_code` (for failures), `error_fingerprint`
- payload size hints (`job_payload_bytes`, `event_payload_bytes`) if cheap to compute

Goal: identify whether memory increases on specific message classes or error paths.

### C) Retry lifecycle logging (poison detection)

For each failure, log:
- `attempt_number`, `max_attempts`
- `next_retry_seconds`
- `terminal_decision` (`retry`, `dead_letter`, `archive`)
- `terminal_reason` (e.g., `foreign_key_violation_non_retriable`)

Goal: prove bounded retry behavior in production and eliminate silent infinite loops.

### D) High-watermark forensic logging

When RSS crosses thresholds (for example 70%, 85%, 95% of 512 MB):
- Emit one-time snapshot logs with:
  - top object growth sample (`tracemalloc` top stats diff)
  - count of cached/pending in-memory items
  - current message context
- Throttle to avoid log spam.

Goal: capture "what is growing" before process recycle.

## Additional Things To Try

1. **Force deterministic non-retriable handling**
   - Classify DB integrity errors like `23503` as terminal and dead-letter/archive immediately.

2. **Add retry cap guardrails at queue boundary**
   - Even if app logic fails open, queue-level max retry should stop infinite churn.

3. **Run controlled canary with debug memory logs**
   - Enable diagnostics for one worker instance for 1-2 hours.
   - Compare memory slope during normal jobs vs intentionally poisoned jobs.

4. **Verify defaults vs explicit env for queue/table names**
   - Set explicit values in Render config temporarily to remove ambiguity during investigation.

5. **Capture one live heap profile near 85-95% memory**
   - Use `tracemalloc` snapshots or equivalent and persist artifact for comparison across runs.

## Validation Plan (Updated)

1. Inject one known-invalid message (`run_id` missing parent).
2. Confirm retries stop at expected cap and message reaches terminal state.
3. Confirm logs show `terminal_decision=dead_letter` (or archive) for deterministic FK failures.
4. Run worker for 60+ minutes under representative load.
5. Verify memory chart no longer shows repeated climb-to-limit sawtooth.
6. Verify no repeated error bursts for same `run_id`/`msg_id`.
7. Verify dead-letter queue depth and alerting behavior.

## Notes

- The current evidence still points first to retry semantics and poison-message handling.
- We cannot conclusively rule out an additional in-process memory retention issue until heap/memory-delta instrumentation is live.

---

## Implementation Summary (2026-03-13)

The following changes were implemented:

1. **Non-retriable classification** — SQLSTATE `23503` (FK violation) and `23505` (unique violation) are now treated as terminal; no retries.
2. **Read-count ceiling** — Messages with `read_count >= 20` are forced to terminal to prevent infinite churn.
3. **Memory diagnostics** — Optional heartbeat, per-message delta, and high-watermark logs (gated by `WORKER_MEMORY_DIAGNOSTICS_ENABLED=1`).
4. **Env vars** — `WORKER_MEMORY_DIAGNOSTICS_ENABLED`, `WORKER_MEMORY_LIMIT_MB`, `WORKER_MEMORY_HEARTBEAT_INTERVAL_SECONDS`.

---

## Manual Validation and Investigation Steps

### 1. Deploy and verify non-retriable behavior

- Deploy the worker with the new code.
- Purge or reconcile any existing poison messages in the queue (run_ids with missing `pipeline_runs` parent).
- Trigger a run that will produce an FK violation (e.g. enqueue a message with a `run_id` that has no `pipeline_runs` row).
- **Expected:** Logs show `worker_non_retriable_terminal` and message is archived immediately. No `worker_retry_scheduled` for that message. No repeated FK error bursts for the same `run_id`.

### 2. Enable memory diagnostics for investigation

- In Render, set `WORKER_MEMORY_DIAGNOSTICS_ENABLED=1` for the worker service.
- Optionally set `WORKER_MEMORY_HEARTBEAT_INTERVAL_SECONDS=30` for more frequent heartbeats.
- Restart the worker.
- **Expected:** Logs show `worker_memory_heartbeat` every 30–60s and `worker_memory_message_delta` at message boundaries.

### 3. Monitor memory chart and logs

- Watch the Render memory chart for 60+ minutes.
- **Expected:** If poison-message handling is effective, the sawtooth pattern should stop or reduce. Memory may still climb during normal pipeline runs; the key is no repeated sharp resets from restarts.
- If memory still climbs: correlate `worker_memory_message_delta` logs with `result` and `error_code` to identify which paths increase memory.

### 4. High-watermark snapshot confirmation

- If memory approaches 70%, 85%, or 95% of the limit, logs should show `worker_memory_high_watermark` with top allocations.
- **Expected:** One-time snapshot per threshold with `tracemalloc` top stats. Use this to identify allocation hotspots.

### 5. Regression checks

- Run a normal successful pipeline from the UI.
- **Expected:** Job succeeds, run status `succeeded`, message archived. No unexpected terminal handling.
- Run a pipeline that fails transiently (e.g. temporary API error).
- **Expected:** Retries occur up to the configured cap, then terminal. Logs show `worker_retry_scheduled` and eventually `failed` status.

### 6. Tech-debt follow-up

- See `docs/tech-debt/td-2026-03-13-retry-error-propagation-validation.md` for a planned deep validation of retry error propagation when time permits.
