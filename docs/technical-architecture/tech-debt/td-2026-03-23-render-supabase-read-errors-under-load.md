# Tech Debt: Render/Supabase read errors under load

## ID

- `td-2026-03-23-render-supabase-read-errors-under-load`

## Status

- Open

## Where

- **API request paths:** `app/routes/management.py` (`GET /management/account`), `app/routes/ui_theme.py` (`GET /theme/runtime`)
- **Supabase-backed reads:** `app/services/supabase_auth_repository.py` (`get_profile`), `app/repositories/postgres_ui_theme_repository.py` (`get_active_preset_id`, `get_preset_by_id`)
- **Client wiring:** `app/integrations/supabase_client.py` (shared sync Supabase client created once and reused)
- **Related worker/client lifecycle evidence:** `docs/technical-architecture/incident_investigations/worker_memory_starvation_2026-03-13/network_fd_leak_remediation.md`

## Observed behavior

- Production Render logs show intermittent **500** responses on `GET /management/account` while the service is otherwise alive and still answering `GET /health` with **200**.
- The same failure window also shows `GET /theme/runtime` failing during a read of the active UI theme preset.
- Both traces terminate in `postgrest` -> `httpx` / `httpcore` sync transport code with `httpx.ReadError` / `httpcore.ReadError: [Errno 11] Resource temporarily unavailable`.
- The failing reads are small, hot-path account/theme lookups that should be cheap and stable; this points to request-path transport/resource contention rather than a logical bug in the route handlers themselves.

## Steps to reproduce

1. Run the current Render API and worker topology in production-like sizing.
2. Sign into the dashboard and load flows that call `GET /management/account` and `GET /theme/runtime`.
3. At the same time, allow the worker and other authenticated API traffic to continue making Supabase/PostgREST calls.
4. Observe intermittent 500s in the API logs with `httpx.ReadError` / `httpcore.ReadError: [Errno 11] Resource temporarily unavailable` on the above routes.

## Expected behavior

- Authenticated dashboard reads such as `/management/account` and `/theme/runtime` should remain reliable under normal concurrent API + worker load.
- A healthy API process should not return 500 for these hot reads because of HTTP transport pool exhaustion, socket pressure, or shared-client contention.
- Render instance sizing and client/pool configuration should be explicit enough that we can predict safe concurrency rather than infer it from failures.

## Why this exists / notes

- **Proven from logs:** the failing calls are read-only Supabase/PostgREST requests made from API routes that otherwise have straightforward logic.
- **Proven from code:** these paths use the long-lived sync Supabase client created in `app/integrations/supabase_client.py`, which ultimately uses `httpx` under the hood.
- **Related proven background:** the earlier worker investigation confirmed at least one concrete socket/session lifecycle problem in our Supabase usage pattern (`client.schema("public")` creating fresh schema clients with their own `httpx.Client` sessions on queue RPC paths).
- **Inferred:** current Render service sizing, shared sync client behavior, and HTTP/2 transport/pooling defaults may be an unsafe combination once API requests and worker traffic overlap.
- **Still unproven:** whether the primary trigger is instance undersizing, file descriptor pressure, `httpx` HTTP/2 behavior, thread-safety of the shared sync client under concurrent access, or a combination of the above.

## Goal

- Eliminate transient `Errno 11` read failures from authenticated hot paths in production.
- Establish an explicit, validated architecture for Supabase/PostgREST client lifecycle, pooling, and retry/degradation behavior on both API and worker services.
- Reduce unnecessary repeat reads for low-churn account/theme data so the backend is not doing avoidable work on every page load.

## Suggested resolution push

### 1. Capacity and right-sizing baseline

1. Capture per-service metrics during the failure window: CPU, memory, open FDs, socket counts, request rate, worker concurrency, and Supabase/PostgREST latency/error rate.
2. Compare current Render instance classes for API and worker against observed peaks, not idle averages.
3. Right-size API and worker independently; do not assume the same instance profile is correct for both roles.
4. Document the target operating envelope: expected concurrent requests, worker parallelism, and the headroom required before saturation.

### 2. HTTP client / connection pooling remediation

1. Audit every long-lived Supabase/PostgREST access path to identify where we share a sync client across threads, create per-call schema clients, or rely on implicit `httpx` defaults.
2. Validate whether the current transport is using HTTP/2 and whether that is helping or hurting under our workload.
3. Move to an explicit client-lifecycle strategy for API and worker services:
   - one well-owned long-lived client/transport per process where safe,
   - no hidden per-call session creation,
   - explicit shutdown/close hooks,
   - explicit connection limits, keepalive limits, and timeouts instead of library defaults.
4. If testing shows shared sync-client access is unsafe under worker/API concurrency, split clients by service role or execution context rather than letting unrelated traffic contend on the same transport assumptions.
5. Add focused logging/metrics around pool waits, retries, transport errors, and fallback behavior so a future regression is diagnosable without raw stack traces alone.

### 3. Cache low-churn account responses

1. Add a short-lived server-side cache for low-churn reads that are requested frequently by the dashboard, starting with:
   - account/profile payload returned by `GET /management/account`
   - active theme runtime payload returned by `GET /theme/runtime`
2. Use small TTLs appropriate for operator edits, for example tens of seconds to a few minutes, and keep invalidation simple:
   - invalidate account cache on profile/admin limit changes for that user
   - invalidate theme cache on preset create/update/delete/activate
3. Treat caching as load reduction, not as the sole fix; transport/pool correctness still has to stand on its own.
4. Prefer graceful fallback where safe, for example default theme payload on theme-read failure, but only when that does not hide correctness problems.

### 4. Validation and rollout

1. Reproduce the failure in a controlled environment with realistic API traffic plus worker activity.
2. Test candidate pool settings and transport strategies under load before changing production defaults.
3. Roll out in phases:
   - observability + metrics
   - pooling/client lifecycle fix
   - cache layer
   - Render right-sizing adjustment based on the new baseline
4. Success criteria:
   - no `Errno 11`/`ReadError` bursts on `/management/account` or `/theme/runtime`
   - stable FD/socket counts over time
   - reduced Supabase read volume for repeated dashboard loads
   - no user-visible regression when profile limits or theme settings change

## Out of scope for this note

- Replacing Supabase/PostgREST with a different persistence stack.
- Broad async rewrites of the entire backend.
- UI-only work unrelated to backend read pressure or request reliability.
