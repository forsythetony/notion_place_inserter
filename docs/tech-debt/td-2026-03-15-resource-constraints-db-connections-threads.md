# Tech Debt Story: Resource Constraints Analysis (DB Connections and Threads)

## ID

- `td-2026-03-15-resource-constraints-db-connections-threads`

## Status

- Backlog

## Why this exists

Phase 4 deployment exposed resource contention under load: deployed worker logs (2026-03-15) showed `Errno 11` (Resource temporarily unavailable) in `id_mapping` lookups and foreign key violations when `save_pipeline_run` failed silently while parallel pipelines continued. The worker uses `ThreadPoolExecutor` for parallel pipeline execution, and all threads share a single Supabase client. Supabase/PostgREST and the underlying httpx client have connection and concurrency limits that are not well understood or documented.

Without a focused analysis, we risk:
- repeated Errno 11 and FK violations under production load,
- connection pool exhaustion or socket leaks as traffic scales,
- thread-safety issues when multiple threads share the same Supabase client,
- inability to size infrastructure or tune parallelism without empirical data,
- and cascading failures when Supabase free/starter tier limits are hit.

## Goal

Analyze and document resource constraints for database connections and thread usage so we can tune parallelism, connection handling, and infrastructure sizing with confidence.

## In Scope

- **Database connections**
  - Map all Supabase client usage paths (API, worker, queue, run repo, id_mapping, seed service, etc.).
  - Document whether the Supabase Python client is thread-safe and how it manages connections.
  - Identify connection pool behavior (if any) and per-request vs. long-lived connection patterns.
  - Measure or estimate connection usage under typical and peak load (e.g., one job with N parallel pipelines).
  - Compare against Supabase connection limits (free vs. paid tiers) and PostgREST behavior.

- **Thread usage**
  - Enumerate all thread creation points (e.g., `ThreadPoolExecutor` in `job_execution_service._run_parallel_pipelines`).
  - Document max concurrent threads and what each thread does (DB calls, external APIs, CPU work).
  - Identify shared mutable state and thread-safety risks (e.g., single Supabase client across threads).
  - Assess whether sequential pipeline execution is a viable fallback and under what conditions.

- **Validation and instrumentation**
  - Add or extend metrics/logging for connection count, thread count, and Errno 11 frequency.
  - Run load tests (local and/or staging) to reproduce Errno 11 and connection exhaustion.
  - Document recommended settings (e.g., `pipeline_run_mode=sequential` vs. `parallel`, worker poll interval).

## Out of Scope

- Rewriting the Supabase client or switching to a different DB client.
- Full async migration (unless analysis strongly recommends it).
- Infrastructure changes beyond configuration tuning.

## Suggested Validation Tasks

1. **Connection mapping**
   - Trace every `self._client.table(...)`, `client.schema(...)`, and `client.rpc(...)` call.
   - Note which paths create new sessions vs. reuse existing (see `network_fd_leak_remediation.md`).
   - Document Supabase Python client internals (httpx usage, connection pooling).

2. **Thread mapping**
   - List all `ThreadPoolExecutor`, `Thread`, or `concurrent.futures` usage.
   - For `_run_parallel_pipelines`: document max workers = `len(pipelines_data)` and typical pipeline count per stage.
   - Identify any other concurrent execution (asyncio, multiprocessing).

3. **Load testing**
   - Run a single job with multiple parallel pipelines (e.g., notion_place_inserter job) and capture:
     - Errno 11 occurrence rate,
     - connection/socket count over time,
     - thread count.
   - Repeat with `pipeline_run_mode=sequential` and compare.
   - Run multiple concurrent jobs (if supported) to stress connection limits.

4. **Documentation**
   - Produce a resource-constraints summary: recommended parallelism, connection limits, and failure modes.
   - Add runbook guidance for "Errno 11" and "connection pool exhausted" symptoms.
   - Capture follow-up tickets for connection pooling, thread-safety fixes, or sequential fallback.

## Acceptance Criteria

- All Supabase client usage paths are documented with connection/session behavior.
- All thread creation points are documented with concurrency and shared-state notes.
- At least one load test reproduces or rules out Errno 11 under realistic conditions.
- A resource-constraints summary document exists with recommended settings and failure-mode guidance.
- Follow-up implementation tasks are captured for any high-risk findings.

## Primary Code Areas to Review

- `app/integrations/supabase_client.py` — client creation and configuration
- `app/services/supabase_queue_repository.py` — schema-scoped client usage (see `network_fd_leak_remediation.md`)
- `app/repositories/postgres_run_repository.py` — run persistence, id_mapping calls
- `app/repositories/id_mapping.py` — `resolve_or_create_mapping` (retry added for Errno 11)
- `app/services/job_execution/job_execution_service.py` — `_run_parallel_pipelines`, `ThreadPoolExecutor`
- `app/worker_main.py` — single Supabase client shared by worker loop and job execution
- `app/queue/worker.py` — poll loop, message handling

## Related Docs

- `docs/incident_investigations/worker_memory_starvation_2026-03-13/network_fd_leak_remediation.md` — socket leak from queue RPC path
- `temp/deployed_worker-logs_2026-03-15_16-11-42.log` — Errno 11 and FK violations in production
- `docs/planning/multi-tenant-productization-prd/technical/phase-4-datastore-backed-definitions/phase4-deployment-guide.md` — deployment context

## Notes

- Errno 11 (EAGAIN) typically indicates socket read would block; under connection contention, multiple threads hitting the same client can trigger it.
- The 2026-03-15 fixes (fail-fast on `save_pipeline_run`, retry in `id_mapping`) mitigate symptoms but do not address root cause of connection/thread contention.
- Supabase free tier has limited connections; Render starter worker may have resource constraints that amplify contention.

## Temporary Mitigation (Implemented 2026-03-15)

As a short-term workaround, the bootstrap job stages use `pipeline_run_mode: sequential` instead of `parallel`. This reduces concurrent DB usage and avoids Errno 11 under current shared-client architecture. **This is not the final state.** Revert to parallel once this story is completed and connection/thread handling is improved.

- Bootstrap YAML: `product_model/bootstrap/jobs/notion_place_inserter.yaml` — stages set to sequential with inline comments.
- Manual backfill for existing owners: `docs/sql/manual/backfill_stage_run_mode_sequential.sql` (run in Supabase Dashboard).
- Deployment guide: [Phase 4 Deployment Guide](../planning/multi-tenant-productization-prd/technical/phase-4-datastore-backed-definitions/phase4-deployment-guide.md) — "Temporary Sequential Mitigation" section.
