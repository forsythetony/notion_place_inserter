# Render API web service — slow or failed startup after successful build

**Date:** 2026-03-23  
**Status:** Complete on 2026-03-23 (findings from runtime logs; deploy-stop reason not confirmed in Events)

## Scope and sources

- Render **build** log (earlier): successful `pip` install and upload.
- Render **runtime** log (same incident): `app.env_bootstrap` masked env dump, `postgres_seed_service` bootstrap, Uvicorn INFO lines (see sanitized excerpt below).
- **Not used:** Render **Events** timeline (would confirm whether shutdown was deploy swap, manual restart, or health-driven restart).

## Impact

- **User report:** API “struggling to come up” on Render.
- **From logs:** The process **did** reach “Application startup complete” and listened on **`0.0.0.0:10000`** — so this slice is **not** a bind/port failure or immediate crash after import.
- **Shutdown:** ~42s after listen, Uvicorn logged a **graceful** shutdown (`Shutting down` → `Application shutdown complete`). That pattern is consistent with **SIGTERM** (e.g. deploy replacing an instance, service restart, or platform stop), not a typical OOM kill (which usually does not produce orderly Uvicorn shutdown logs).

## Timeline

1. **2026-03-23 ~05:49:28Z** — Env bootstrap logging (`app.env_bootstrap:log_env_masked`).
2. **~05:49:31Z** — `bootstrap_seed_catalog_complete` (`app.services.postgres_seed_service:seed_catalog_if_needed`).
3. **~05:49:33Z** — `Application startup complete.` then `Uvicorn running on http://0.0.0.0:10000`.
4. **~05:50:15Z** — Graceful shutdown sequence; process exit.

**Durations (approx.):** ~5s from first log line to “running”; ~42s from “running” to shutdown.

## Observed behavior

- **Binding:** Correct for Render — `0.0.0.0` and port **10000** (Render sets `PORT`; matches platform expectation).
- **Startup work:** One-shot catalog seed finished before “startup complete” (~3s between env dump and seed line).
- **No** traceback, **no** health-check failure line in this excerpt (Render often reports health outside app stdout).
- **Shutdown:** Orderly Uvicorn shutdown, worker pid **45** ended cleanly.

## Analysis

### Root cause (or leading hypothesis)

1. **Ruled out (for this log window):** Wrong host/port (`127.0.0.1` / ignoring `PORT`) — Uvicorn explicitly bound `0.0.0.0:10000`.
2. **Ruled out (weak evidence):** Immediate crash on boot — startup completed and server accepted the event loop until shutdown.
3. **Leading explanation for “struggling”:** **Perceived latency or deploy churn**, not total failure to start:
   - **Cold start:** Env logging + DB seed adds a few seconds before the service is ready; health checks or clients may retry during that window.
   - **Graceful stop ~42s later:** Most consistent with **platform-initiated stop** (new deploy cutting over, one-off restart, or instance recycle). Confirm in Render **Events** for the service at the same timestamps.
4. **If** the service was flapping: this excerpt shows **one** clean cycle only; capture **longer** logs or Events to see restart loops or failed health checks.

**Confidence:** **High** that the app reached a healthy listening state on this run; **medium** that user-facing “struggle” was delay/deploy lifecycle rather than a hard boot error; **low** without Events for why shutdown occurred.

### What we cannot prove from available evidence

- Whether Render marked the deploy **healthy** and when.
- Whether shutdown was **blue/green deploy**, **manual restart**, **suspended service**, or another trigger.
- Whether any **502** seen by clients happened on a different instance or during a different window.

## Remediation and follow-up

1. **Correlate shutdown** — In Render: **Events** / **Deploy** for `~05:50:15Z` UTC on 2026-03-23; note “instance stopped”, “deploy live”, or similar.
2. **If cold start is too slow for health checks** — Ensure the health check path is fast, increase **initial grace** or timeout if seed work grows; consider deferring non-critical seed to background (product decision).
3. **Operational clarity** — Keep a one-line INFO log when ready to accept traffic (in addition to Uvicorn’s line) so deploy logs are easy to scan.

## Recommendations (logging / alerts / process)

- **Do not** paste full env values into tickets or docs; publishable/secret keys must stay redacted in shared artifacts.
- **Alert** on sustained **unhealthy** state or **restart loop** for the API service, not only on build failure.
- Optional: document **expected** first-request latency after deploy if seed/catalog work is required at startup.

## Sanitized log excerpt

> Original raw lines contained **unredacted** `SUPABASE_PUBLISHABLE_KEY` and other identifiers. They were **removed from this repo** and replaced with a redacted excerpt. Keep secrets out of git; rotate any key that was pasted into a tracked file.

```
2026-03-23T05:49:28Z  INFO  app.env_bootstrap:log_env_masked  env | BASE_URL=https://…onrender.com
2026-03-23T05:49:28Z  INFO  app.env_bootstrap:log_env_masked  env | SECRET=********************************************
2026-03-23T05:49:28Z  INFO  app.env_bootstrap:log_env_masked  env | CORS_ALLOWED_ORIGINS=https://…onrender.com
2026-03-23T05:49:28Z  INFO  app.env_bootstrap:log_env_masked  env | SUPABASE_PROJECT_REF=<redacted>
2026-03-23T05:49:28Z  INFO  app.env_bootstrap:log_env_masked  env | SUPABASE_URL=https://<ref>.supabase.co
2026-03-23T05:49:28Z  INFO  app.env_bootstrap:log_env_masked  env | SUPABASE_PUBLISHABLE_KEY=<redacted>
2026-03-23T05:49:28Z  INFO  app.env_bootstrap:log_env_masked  env | SUPABASE_SECRET_KEY=*****************************************
… (additional masked/unset env lines) …
2026-03-23T05:49:31Z  INFO  app.services.postgres_seed_service:seed_catalog_if_needed  bootstrap_seed_catalog_complete
2026-03-23T05:49:33Z  INFO  Application startup complete.
2026-03-23T05:49:33Z  INFO  Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-03-23T05:50:15Z  INFO  Shutting down
2026-03-23T05:50:15Z  INFO  Waiting for application shutdown.
2026-03-23T05:50:15Z  INFO  Application shutdown complete.
2026-03-23T05:50:15Z  INFO  Finished server process [45]
```
