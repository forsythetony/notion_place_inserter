# Worker Memory Starvation Investigation (2026-03-13)

## Scope

- Service: `notion-pipeliner-worker` (Render)
- Signals reviewed:
  - Render memory chart screenshot (512 MB limit)
  - Runtime logs in `logs.txt`

## Executive Finding

This does **not** look like a classic slow memory leak from normal traffic.  
It looks like a **crash/restart cycle caused by repeated poison-message retries**, with memory climbing toward the 512 MB cap between restarts.

Confidence: **medium-high** (pattern matches logs and worker retry semantics).

## Evidence

1. **Sawtooth memory pattern with hard resets**
   - Screenshot shows memory ramping from roughly 20-30% to ~95-100%, then dropping sharply.
   - Sharp drops are consistent with process restart/recycle, not with steady-state GC behavior.

2. **Frequent worker restarts in logs**
   - Multiple fresh starts: `==> Running 'python -m app.worker_main'` around `19:31`, `19:42`, and `19:49`.
   - Indicates the process is repeatedly restarted (platform recycle, deploy, or crash recovery).

3. **Repeated identical job failures every ~5 minutes**
   - Same `run_id` values repeatedly fail with FK violations:
     - `pipeline_run_events_run_id_fkey`
     - `Key (run_id)=... is not present in table "pipeline_runs"`
   - `worker_starting` logs `vt_seconds=300`, and failed messages are retried at that cadence.
   - This is a poison-message loop: the message becomes visible again and is reprocessed indefinitely.

4. **Worker behavior allows infinite retries on this class of failure**
   - In `app/queue/worker.py`, unexpected processing errors are logged and message is intentionally not archived, so it reappears after visibility timeout.
   - When persistence of "running" state fails, execution raises and returns to loop; repeated failures re-trigger full processing path.

## Likely Root Cause Chain

1. Run persistence integrity issue (missing `pipeline_runs` parent row for a queued job).
2. Worker attempts `insert_event`, gets FK violation, raises.
3. Message is not archived/dead-lettered, so it reappears after 300s.
4. Same failing payload is retried forever.
5. Repeated exception + reprocessing cycle drives memory growth until process recycle/OOM threshold.

## Recommendations

## 1) Stop the bleeding (immediate)

- Add a **retry limit + dead-letter strategy** for worker messages.
- For deterministic data-integrity errors (e.g., FK 23503), **archive or dead-letter immediately** instead of retrying forever.
- Add alerting for repeated same `run_id`/`msg_id` failures over a short window.

## 2) Fix data integrity preconditions (high priority)

- Guarantee `pipeline_runs` row exists before message enqueue (transaction or strict ordering).
- Add pre-flight guard in worker:
  - If `run_id` missing, mark job/run as failed with explicit reason and archive message.
- Reconcile or purge already-poisoned queue entries tied to missing `pipeline_runs`.

## 3) Add memory diagnostics (high priority)

- Instrument memory per loop iteration (RSS), and log with `run_id`, `msg_id`, outcome.
- Capture heap snapshots / `tracemalloc` diffs on high watermark crossings.
- Add a metric for "retries per message" and "poison messages".

## 4) Resilience and operability (medium priority)

- Add circuit-breaker behavior: if same error signature repeats N times, back off and page.
- Consider reducing in-memory payload retained in exception paths and event bus callbacks.
- Keep worker at 1 message per pull until poison-message handling is in place (already true with `batch_size=1`).

## Validation Plan After Fixes

1. Seed one intentionally invalid queued message (missing parent run row).
2. Verify worker classifies it as non-retriable (dead-letter/archive) within bounded retries.
3. Run worker for 60+ minutes and confirm memory stabilizes below alert threshold.
4. Confirm no repeated FK failure log spam for same `run_id`.
5. Confirm queue depth drains and does not oscillate on same message IDs.

## Notes

- The chart strongly suggests restart-driven resets; logs include both deploy-related restart and recurring runtime restarts.
- Without heap profiling, we cannot prove a pure allocator leak in application code. Current evidence points first to **unbounded poison-message retry behavior** as the primary trigger.
