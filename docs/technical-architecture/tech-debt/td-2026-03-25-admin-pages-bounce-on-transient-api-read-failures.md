# Tech Debt: Admin pages bounce to dashboard on transient API read failures

## ID

- `td-2026-03-25-admin-pages-bounce-on-transient-api-read-failures`

## Status

- Open

## Where

- **UI repo / backend / surface:** `notion_pipeliner_ui` admin routes backed by `app/` management and admin APIs
- **Primary files or routes:** `notion_pipeliner_ui/src/routes/AdminUsersPage.tsx`, `notion_pipeliner_ui/src/routes/AdminThemePage.tsx`, `notion_pipeliner_ui/src/routes/AdminMonitoringPage.tsx`, `notion_pipeliner_ui/src/layouts/AppShell.tsx`, `notion_pipeliner_ui/src/lib/api.ts`
- **Related API paths:** `GET /management/account`, `GET /theme/runtime`, `GET /auth/admin/runs`
- **Related existing investigation:** [`td-2026-03-23-render-supabase-read-errors-under-load.md`](./td-2026-03-23-render-supabase-read-errors-under-load.md)

## Observed behavior

- In production on `https://oleo.sh`, admin navigation can be hit-or-miss on `/admin/users`, `/admin/theme`, and `/admin/monitoring`.
- Browser devtools show CORS-style failures for requests from `https://oleo.sh` to `https://api.oleo.sh`, including:
  - `GET /management/account`
  - `GET /auth/admin/runs?limit=50&offset=0`
- When this happens, the page may load slowly, fail to finish loading, or redirect back to `/dashboard`.
- Live verification against the deployed API shows this is **not** a steady allowlist mistake:
  - `GET /health` with `Origin: https://oleo.sh` returns `Access-Control-Allow-Origin: https://oleo.sh`
  - preflight `OPTIONS /management/account` from `https://oleo.sh` returns `Access-Control-Allow-Origin: https://oleo.sh`
  - preflight `OPTIONS /auth/admin/runs` from `https://oleo.sh` returns `Access-Control-Allow-Origin: https://oleo.sh`

## Steps to reproduce

1. Sign into production as an admin user on `https://oleo.sh`.
2. Navigate between `/admin/users`, `/admin/theme`, and `/admin/monitoring`.
3. During a failure window, watch the browser network/devtools output.
4. Observe intermittent failures on `GET /management/account` and sometimes `GET /auth/admin/runs`, reported by the browser as blocked by CORS / `net::ERR_FAILED`.
5. Observe that the admin page may redirect to `/dashboard` even though the user session is still valid.

## Expected behavior

- Admin routes should remain on the current page and show a retryable error state when a supporting API call transiently fails.
- Redirecting away from an admin route should happen only on confirmed auth/authorization failure (for example 401/403 or a successful account payload showing a non-admin user), not on generic network or transport errors.
- Production errors should be diagnosable as backend/service failures rather than surfacing only as misleading browser CORS messages.

## Why this exists / notes

- **Proven from live checks:** the deployed API currently allows `https://oleo.sh` in CORS for the tested routes, so the browser error text is masking another failure mode rather than proving a persistent CORS config bug.
- **Proven from frontend code:** `AdminUsersPage`, `AdminThemePage`, and `AdminMonitoringPage` all gate access by calling `getManagementAccount(accessToken)` and setting gate state to `"denied"` on any `.catch(...)`, which immediately redirects to `/dashboard`.
- **Proven from frontend code:** `AppShell` is more resilient and keeps cached admin chrome on transient `getManagementAccount` failures, so the bounce is page-specific rather than a full-session sign-out.
- **Likely related:** the existing production investigation for `GET /management/account` and `GET /theme/runtime` already documents intermittent backend read failures (`httpx.ReadError` / `httpcore.ReadError`) under load. This admin-route symptom is consistent with that instability.
- **Still unproven:** whether `GET /auth/admin/runs` is failing for the same transport/resource-contention reason as `GET /management/account`, or whether it has an additional query/load-specific issue.

## Goal

- Stop transient backend/API failures from ejecting admins out of admin pages.
- Distinguish transport/service unavailability from true authorization denial in the frontend route gating.
- Extend backend investigation so `GET /auth/admin/runs` is either confirmed as the same failure class or isolated separately.

## Suggested follow-ups

### 1. Frontend logging and correlation

1. Add a lightweight request wrapper for admin bootstrap requests (`GET /management/account`, `GET /theme/runtime`, `GET /auth/admin/runs`) that records:
   - route / page name
   - request path
   - start/end timestamp and latency
   - result class (`ok`, `401`, `403`, `status_5xx`, `network_error`, `aborted`)
   - whether the page redirected afterward
2. Generate a per-page-load correlation id in the browser and send it as a request header (for example `X-Request-ID` or `X-Oleo-Request-ID`) so frontend failures can be matched to API logs.
3. Preserve the current browser-visible failure shape before redirecting:
   - `ApiError.status`
   - `ApiError.detail`
   - current pathname
   - whether this came from admin gate logic or a later data fetch
4. If we add browser error reporting, prefer a tool that captures console/network breadcrumbs and route transitions so the “CORS” message can be seen next to the redirect event.

### 2. API logs to add immediately

1. Add structured `loguru` request logs around the three hot paths:
   - request start
   - request finish
   - exception / transport error
2. Include the following fields on every log line for these routes:
   - request id / correlation id
   - route path and method
   - user id (if authenticated)
   - user type
   - response status
   - duration ms
   - Render instance id / process id if available
3. For the backend reads behind these routes, log the exact stage that failed:
   - auth/profile fetch
   - theme preset lookup
   - admin runs query
   - downstream Supabase/PostgREST call
4. On exceptions, log the transport-specific details that are currently getting lost behind the browser CORS error:
   - exception class (`httpx.ReadError`, `httpcore.ReadError`, timeout, etc.)
   - errno/message
   - retry count if any
   - whether the failure happened before response headers, during body read, or after partial success
5. Add explicit timeout logging so we can distinguish “slow then failed” from “fast hard failure.”

### 3. Metrics and traces worth adding

1. Add counters and latency histograms for:
   - `management_account_requests_total`
   - `theme_runtime_requests_total`
   - `admin_recent_runs_requests_total`
   - matching `*_failures_total`
   - matching latency histograms / percentiles
2. Break failures down by class:
   - `4xx`
   - `5xx`
   - network/transport
   - upstream Supabase/PostgREST
3. Add gauges or periodic logs for process pressure during the failure window:
   - open file descriptors
   - socket count
   - thread count
   - memory
   - worker concurrency / queue depth
4. Reuse the direction in [`error-handling-observability-and-telemetry.md`](../productization-technical/beta-launch-readiness/error-handling-observability-and-telemetry.md):
   - current state: structured logs via `loguru`, no OTEL yet
   - likely next step: OTEL traces/metrics or another centralized facade so request traces can follow API -> Supabase/PostgREST

### 4. External tooling that would help

1. **Render metrics/logs**
   - correlate request failures with CPU, memory, restarts, deploys, and instance saturation
   - compare API vs worker pressure in the same time window
2. **Supabase logs / query insights**
   - confirm whether failing windows line up with PostgREST errors, latency spikes, pool exhaustion, or auth/profile lookup issues
3. **Cloudflare analytics/logs** if available for `api.oleo.sh`
   - confirm whether some failures are edge/proxy resets or origin disconnects before CORS headers are added
4. **Browser error reporting** such as Sentry
   - useful for capturing route breadcrumb -> failed fetch -> redirect sequence from real users
5. **Distributed tracing / OTEL backend** such as Grafana Cloud, Honeycomb, or Datadog
   - useful once request ids and instrumentation exist, especially to see whether failures cluster in specific downstream Supabase calls

### 5. Short-term diagnostic experiments

1. Add temporary elevated logging only for these endpoints in production for a limited window so we can capture one failing sequence end-to-end without flooding logs everywhere else.
2. Run a small synthetic probe from outside the browser:
   - periodic authenticated `GET /management/account`
   - periodic authenticated `GET /auth/admin/runs`
   - record status, latency, and response headers
   This would help separate browser-only symptoms from general origin instability.
3. Reproduce with controlled concurrent worker/API traffic and compare:
   - baseline idle
   - API-only load
   - worker-heavy load
   - mixed load
4. Test whether disabling redirect-on-catch in the admin gate changes the observed symptom from “bounce to dashboard” to a stable inline failure state, which will make the underlying backend issue much easier to inspect.
5. Consider lightweight caching or other load-reduction for account/admin bootstrap reads, but only after transport/client reliability is better instrumented.

## Out of scope for this note

- Replacing the current auth/routing model wholesale.
- Broad UI redesign of admin pages unrelated to transient API failure handling.
- Final root-cause closure of the backend read-failure investigation; this note tracks the user-visible admin-route symptom and redirect behavior.
