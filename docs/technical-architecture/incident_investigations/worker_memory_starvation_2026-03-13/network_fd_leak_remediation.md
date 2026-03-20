# Network FD Leak Remediation Findings

Date: 2026-03-13
Incident: Worker memory starvation (`notion-pipeliner-worker`)
Scope: Confirmed socket leak in idle Supabase queue polling

## Executive Summary

The earlier version of this document was directionally right about "Supabase/PostgREST HTTP," but too speculative about the mechanism.

We now have a much stronger finding:

1. The worker was idle (`msg_id=None`, `run_id=None`) while `fd_socket` rose monotonically.
2. After the redeploy where `WORKER_POLL_INTERVAL_SECONDS=10`, `fd_socket` increased by exactly `+6` per heartbeat minute (`10 -> 16 -> 22 -> 28 -> 34`).
3. Six new sockets per minute matches one leaked socket per 10-second poll.
4. In the idle path, the only repeated network operation is `SupabaseQueueRepository.read()`, which calls `self._client.schema("public").rpc(...).execute()`.
5. Local inspection of the Supabase client confirmed that each `client.schema("public")` call creates a new `SyncPostgrestClient` with its own distinct `httpx.Client` session, and the top-level Supabase client does not expose a public `close()` method.

Most likely root cause: the queue repository allocates a fresh PostgREST/httpx session on every poll and never closes it, causing one leaked socket per queue read.

## What The Evidence Supports

### Runtime evidence

- Idle heartbeats still show FD growth, so this is not dependent on active pipeline execution.
- `fd_socket` is the growing category; `fd_pipe`, `fd_anon`, and `fd_file` stay flat.
- `num_threads` stays flat, which argues against a thread leak.
- RSS rises alongside socket count, which is consistent with unclosed HTTP client/session state.
- Earlier high-watermark traces showed allocations in `httpx`, `httpcore`, `h2`, and `hpack`, which matches the observed socket growth.

### Code evidence

- `app/queue/worker.py` calls `queue_repo.read()` once per poll loop iteration while idle.
- `app/services/supabase_queue_repository.py` uses `self._client.schema("public")` inside `send()`, `read()`, and `archive()`.
- Repeated local inspection showed `client.schema("public")` returns a new `SyncPostgrestClient` each time, with a different underlying `httpx.Client` session each time.
- `app/services/supabase_run_repository.py` does not use this pattern; it operates through `self._client.table(...)`, so the strongest evidence is specifically against the queue repository RPC path rather than every Supabase call equally.

## Correct Root Cause Statement

This is no longer just "a suspected network FD leak somewhere in Supabase reads."

The most accurate current statement is:

> The worker leaks sockets because `SupabaseQueueRepository` constructs a new schema-scoped PostgREST client on every queue RPC call. Each schema-scoped client owns a separate `httpx.Client` session, and those sessions are never closed. During idle polling, that produces one additional open socket per poll.

## Immediate Mitigations

These are rate-limiters, not the fix:

1. Keep `WORKER_POLL_INTERVAL_SECONDS=10` in production until the code fix ships.
2. Keep `WORKER_MEMORY_DIAGNOSTICS_ENABLED=1`.
3. Keep `WORKER_MEMORY_TRACEMALLOC_ENABLED=0` unless actively profiling.
4. Keep the FD category fields in heartbeat logs (`fd_socket`, `fd_pipe`, `fd_anon`, `fd_file`).

Expected outcome before the code fix: slower leak slope, not zero leak.

## Recommended Code Fix

### Primary fix

Stop creating a new schema-scoped client per queue operation.

Recommended implementation:

1. In `SupabaseQueueRepository.__init__`, create one reusable schema-scoped PostgREST client once, for example `self._schema_client = client.schema("public")`.
2. Reuse `self._schema_client` for `pgmq_send`, `pgmq_read`, and `pgmq_archive`.
3. Add an explicit repository/client shutdown hook so the worker can close the underlying `httpx.Client` session on process shutdown.

### Important nuance

The top-level Supabase sync client does not expose a public `close()` method, but the underlying schema-scoped PostgREST client's `session` is an `httpx.Client` and does expose `close()`.

That means the safe direction is:

- own the long-lived schema client explicitly
- reuse it for all queue RPCs
- close its session during worker shutdown

### Fallback guardrail

If we need a belt-and-suspenders mitigation while validating the main fix:

- recycle the worker process or repository client on a fixed cadence
- but treat that only as a temporary safety valve, not the root fix

## Fixes That Are No Longer First Choice

### Periodic full Supabase client recreation

This may reduce blast radius, but it is not the cleanest first fix now that we know the specific allocation site.

### Broad "audit all HTTP transport lifecycle" work

Useful if the primary fix fails, but too broad for the evidence we have today.

### Alternative queue architecture

Not justified yet. We have a concrete, low-scope bug in the current repository implementation.

## Validation Plan

The remediation is successful only if all of the following pass:

1. Idle run for 30 minutes with `WORKER_POLL_INTERVAL_SECONDS=10`:
   - `fd_socket` remains flat or oscillates within a small band.
   - It does not increase by `~6/minute` anymore.
2. Mixed load run for 60 minutes:
   - No sustained socket slope while idle between jobs.
   - No memory sawtooth from repeated restarts.
3. Queue operation regression:
   - `pgmq_read`, `pgmq_send`, and `pgmq_archive` still work normally.
   - Successful runs still archive once.
4. Failure-path regression:
   - Non-retriable `23503`/`23505` handling still goes terminal.
   - No retry loop is reintroduced.
5. Shutdown behavior:
   - Worker exits cleanly.
   - Explicit session close does not raise or hang shutdown.

## Observability Requirements

Keep these heartbeat fields:

- `rss_mb`, `open_fds`
- `fd_socket`, `fd_pipe`, `fd_anon`, `fd_file`
- `num_threads`, `gc_counts`, `gc_objects`
- `msg_id`, `run_id`

Useful alert thresholds:

- Warn if `fd_socket` grows monotonically for 3-5 idle heartbeats.
- Warn if idle FD growth rate approaches `60 / WORKER_POLL_INTERVAL_SECONDS` per minute.
- Warn at memory thresholds 70/85/95%.

## Rollback Plan

If the code fix causes regressions:

1. Revert to the prior worker release.
2. Keep `WORKER_POLL_INTERVAL_SECONDS=10` as the temporary mitigation.
3. Continue heartbeat logging so the socket slope remains visible.
4. Fall back to timed client recycling only if necessary while investigating further.

## Bottom Line

The problem is not merely "Supabase reads might be leaking."

The current evidence points to a specific bug pattern in our code:

- repeated `client.schema("public")`
- one new `httpx.Client` session per queue RPC
- no close path
- one leaked socket per idle poll
