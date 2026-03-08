# Architectural Proposal: Asynchronous Location Processing

## Goal

Convert `POST /locations` from synchronous processing to an asynchronous, queue-backed workflow:

- API performs **basic validation** first.
- If validation passes, API **enqueues a job** and returns immediately.
- Response is **HTTP 200** when enqueue succeeds.
- Pipeline execution moves to a background worker.

This reduces request latency and decouples user-facing API availability from external service variability (Claude, Google Places, Notion).

## Current State (Problem)

Today `POST /locations` validates `keywords`, then runs the full pipeline inline before returning. This means:

- Request latency includes all downstream calls.
- API timeout risk increases with slow dependencies.
- User experience is blocked on processing completion.
- Retries and failure handling are tied to request lifecycle.

## Current Implementation (Phase 1 — In-Memory)

Phase 1 uses an **in-memory** queue and worker inside the FastAPI process:

- **Queue**: `asyncio.Queue` — jobs are held in process memory.
- **Worker**: Background `asyncio` task started in FastAPI lifespan; consumes jobs and runs `PlacesService.create_place_from_query`.
- **Event bus**: In-memory publish/subscribe; success subscriber logs `Pipeline executed successfully!`.

**Constraints (by design for Phase 1):**

- **Single-instance only** — each app instance has its own queue; no cross-instance sharing.
- **Non-durable** — jobs are lost on restart, deploy, or process crash.
- **No retries/DLQ** — failed jobs are logged but not retried or moved to a dead-letter queue.

Future phases can introduce Redis/RQ or SQS for durability and multi-instance support.

## Proposed Target Design (Future Phases)

### High-Level Flow

```text
Client
  -> POST /locations {keywords}
API
  -> Validate request (fast, local checks only)
  -> Publish job to queue
  -> Return 200 {accepted, job_id}

Worker (separate process)
  -> Consume job
  -> Run existing Places pipeline
  -> Record outcome (success/failure)
  -> Emit internal processing signal
Event subscriber (current behavior)
  -> Log "Pipeline executed successfully!"
  -> Future: send user-facing messages/notifications
```

### API Contract

#### Request

`POST /locations`

```json
{
  "keywords": "stone arch bridge in minneapolis"
}
```

#### Validation (before enqueue)

Basic validation should stay lightweight and deterministic:

- `keywords` exists and is a string.
- `keywords.strip()` is not empty.
- Max length guard (for example, 300 chars) to prevent abuse.

If validation fails: return `400` with a clear error message.

#### Success response (enqueue succeeded)

Return immediately with `200`:

```json
{
  "status": "accepted",
  "job_id": "loc_01HR9R8V4W2YQ3A6T9D1X2B7C8"
}
```

Notes:

- `200` is explicitly required for this phase.
- `job_id` is strongly recommended for observability and future status endpoints.

#### Enqueue failure response

If queue publish fails (broker unavailable, serialization error), return `503`:

```json
{
  "detail": "Unable to enqueue request"
}
```

## Components and Responsibilities

### 1) API Layer (`app/routes/locations.py`)

- Keeps auth and request schema checks.
- Performs pre-enqueue validation.
- Delegates to a new enqueue service (`AsyncLocationsService.enqueue(...)`).
- Returns `200` on successful enqueue.

### 2) Producer Service (new, e.g. `app/services/locations_queue_service.py`)

- Builds job envelope and publishes to queue.
- Generates `job_id` and `run_id`.
- Adds metadata for tracing and idempotency checks.

Suggested envelope:

```json
{
  "job_id": "loc_<ulid>",
  "run_id": "<uuid>",
  "created_at": "2026-03-08T12:34:56Z",
  "type": "create_location_from_keywords",
  "payload": {
    "keywords": "stone arch bridge in minneapolis"
  },
  "attempt": 0
}
```

### 3) Queue/Broker

Any durable queue is acceptable. Recommended options:

- **Redis + RQ/Celery** (quickest operationally).
- **SQS + worker** (managed durability).

Required behavior:

- At-least-once delivery.
- Visibility timeout / retry support.
- Dead-letter queue (DLQ) after max attempts.

### 4) Worker Process (new entrypoint)

- Long-running consumer process.
- For each job, executes existing `PlacesService.create_place_from_query(keywords)`.
- Reuses current pipeline architecture; no business-logic rewrite required.
- Logs structured outcome with `job_id`, `run_id`, `attempt`.

### 5) Outcome/Signal Publisher + Subscriber (minimal now, extensible later)

After each terminal job state:

- emit `location.processing.succeeded` or
- emit `location.processing.failed`.

For now, the subscriber behavior should stay intentionally minimal and only log:

`Pipeline executed successfully!`

In a future phase, expand this subscriber to send user-facing messages/notifications.

## Data and State Model

Introduce a lightweight job status store (Redis hash or DB table) to track:

- `job_id`
- `status`: `queued | processing | succeeded | failed`
- `error` (nullable)
- timestamps (`queued_at`, `started_at`, `finished_at`)
- `attempt_count`

This enables operations and future user-facing status APIs, even if not exposed immediately.

## Failure Handling and Reliability

### Retry Policy

- Retry transient failures (network, 429, 5xx) with exponential backoff.
- Do not retry validation/contract errors (bad payload shape after publish should fail fast).

Example policy:

- max attempts: 5
- backoff: 30s, 2m, 10m, 30m, 1h
- then move to DLQ

### Idempotency

Because delivery is at-least-once, duplicate execution is possible.

Mitigation options (choose one initially):

- **Job-level dedupe key**: hash of normalized keywords within a TTL window.
- **Notion insert idempotency marker**: store source `job_id` in a hidden property or metadata to avoid duplicate pages.

Recommendation: start with job-level dedupe plus strong logging; add Notion-level idempotency if duplicate risk is observed.

## Observability

Add structured fields across API + worker logs:

- `job_id`, `run_id`, `attempt`, `queue_name`
- `event`: `enqueue_started`, `enqueue_succeeded`, `enqueue_failed`, `job_started`, `job_succeeded`, `job_failed`, `job_retried`, `job_dead_lettered`
- `duration_ms`

Metrics to track:

- enqueue success rate
- queue depth
- processing latency (queue wait + execution)
- success/failure rate
- retry count / DLQ count

## Security and Validation Boundaries

- Authentication remains on API route.
- Request validation remains pre-enqueue.
- Worker trusts only validated envelope shape and re-validates required fields defensively.
- Never place secrets in queue payloads.

## Incremental Rollout Plan

### Phase 1: Async skeleton (no user notifications)

1. Add queue producer service and worker process.
2. Switch `POST /locations` to validate + enqueue + `200 accepted`.
3. Keep current synchronous path behind feature flag fallback (`LOCATIONS_ASYNC_ENABLED=0/1`).
4. Add logs/metrics and DLQ wiring.

### Phase 2: Hardening

1. Add idempotency strategy.
2. Add job status store and optional `GET /locations/jobs/{job_id}` endpoint.
3. Tune retries and alerting.

### Phase 3: Communications integration

1. Implement event subscriber in communications service.
2. Map job success/failure signals to outbound user notifications.

## API Examples

### Validation failure

```http
POST /locations
Authorization: <secret>
Content-Type: application/json

{"keywords": "   "}
```

```json
{
  "detail": "keywords is required and cannot be empty"
}
```

### Enqueue success (immediate return)

```http
POST /locations
Authorization: <secret>
Content-Type: application/json

{"keywords": "stone arch bridge in minneapolis"}
```

```json
{
  "status": "accepted",
  "job_id": "loc_01HR9R8V4W2YQ3A6T9D1X2B7C8"
}
```

## Key Decisions

- Use **asynchronous request handling via queue** rather than in-request processing.
- Keep **validation at the API boundary** before enqueue.
- Return **HTTP 200** once successfully enqueued (as required).
- Defer user notification delivery; define internal outcome signals now for future integration.

