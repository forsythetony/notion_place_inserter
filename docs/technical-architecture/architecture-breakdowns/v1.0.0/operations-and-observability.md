# Operations and Observability

## Purpose

Capture operational behavior, telemetry model, and architecture-level risks that matter in production and incident response.

## Logging Architecture

`app/main.py` configures Loguru with:

- Console sink (`stderr`)
- Rotating file sink (`LOG_FILE_PATH`, `LOG_FILE_ROTATION`, `LOG_FILE_RETENTION`)
- Custom formatter that appends orchestration metadata when present

`app/pipeline_lib/logging.py` drives structured lifecycle logging through context managers:

- `log_pipeline_request`
- `log_global_pipeline`
- `log_stage`
- `log_pipeline`
- `log_step`
- `log_pipeline_fan_out`
- `log_pipeline_failed_isolated`

## Trace Identity

Pipeline logs are correlated primarily by `run_id`, with nested identifiers:

- `global_pipeline`
- `stage`
- `pipeline`
- `step`
- event fields (`start`, `success`, `failure`, `join_wait`, `join_complete`)
- durations (`duration_ms`)

This enables request-to-step trace reconstruction from logs.

## Async Operational Model

When `LOCATIONS_ASYNC_ENABLED=1`:

- `POST /locations` enqueues and returns immediately with `job_id`.
- A background worker consumes queue items and runs sync pipeline work in an executor.
- Success/failure events are published to in-process event bus subscribers.

Operational implication: there is no built-in persisted job state API; observability is primarily log/event based.

## Configuration Surface

Architecture-affecting env vars include:

- `LOCATIONS_ASYNC_ENABLED` (async queue path vs inline sync execution)
- `DRY_RUN` (no Notion writes)
- `LOCATIONS_CACHE_TTL_SECONDS` (TTL for cached location index used by relation resolution)
- `LOCATION_MATCH_MIN_CONFIDENCE` (threshold for matching existing locations)
- `GOOGLE_PLACE_DETAILS_FETCH` (extra enrichment API calls)
- `LOCATION_RELATION_REQUIRED` (best-effort vs fail-fast relation requirement)
- `LOG_FILE_PATH`, `LOG_FILE_ROTATION`, `LOG_FILE_RETENTION` (log persistence behavior)
- `secret`, `NOTION_API_KEY`, `ANTHROPIC_TOKEN`, `GOOGLE_PLACES_API_KEY`, `FREEPIK_API_KEY`

## Known Constraints and Tradeoffs

### Queue Durability

- Queue is in-memory and process-local.
- Restart/crash loses queued jobs.
- Single-process design limits horizontal scaling semantics.

### Cache Freshness

- Notion schema cache uses TTL pull model (constructor default `300s`; no env override in current wiring).
- Changes in Notion are visible only after expiry or explicit invalidation.
- Location relation matching also uses TTL cache controlled by `LOCATIONS_CACHE_TTL_SECONDS`.

### External Dependency Volatility

- Claude and Google data quality/availability directly influence payload quality.
- Optional integrations (Freepik) can degrade to fallback behavior or no icon.

### Parallel Stage Partial Success

- Property resolution parallel stage isolates per-pipeline failures.
- Result may be partially complete while request still succeeds.
- This favors availability over strict completeness.

## Recommended Operational Practices

- Keep structured logs centralized and searchable by `run_id` and `job_id`.
- Monitor failure event rates per stage/pipeline to identify flaky integrations.
- Use dry-run mode for schema and prompt change validation before enabling writes.
- If reliability requirements increase, replace in-memory queue with durable queue + persisted status store.

## Related Docs

- [Pipeline Architecture](./pipeline-architecture.md)
- [Runtime and Request Flow](./runtime-and-request-flow.md)
- [Services and Integrations](./services-and-integrations.md)
