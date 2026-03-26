# Async Supabase Client Migration

## Problem Statement

The backend uses a **single sync `supabase.Client`** instance shared across all requests via `app.state`. Under the hood, this client uses httpx with HTTP/2, which multiplexes all streams over one TCP connection.

FastAPI runs sync route handlers and sync dependencies (like `require_managed_auth`) in a **threadpool** (`anyio.to_thread.run_sync`). When the browser fires concurrent API calls (e.g. `/management/account` and `/auth/admin/runs` on dashboard load), multiple threadpool workers issue blocking reads on the **same HTTP/2 socket**. This produces intermittent `httpcore.ReadError: [Errno 11] Resource temporarily unavailable` (`EAGAIN`) — even under zero user load.

When an unhandled exception propagates through Starlette's CORS middleware, CORS headers are never set on the response. The browser then reports a misleading "CORS policy" error, masking the real 500.

**Observed on:** 2026-03-26
**Trigger:** Any concurrent API calls from the SPA dashboard
**Root cause:** Sync HTTP/2 connection sharing across threadpool workers

## Proposed Fix: Migrate to Async Supabase Client

Replace the sync `supabase.Client` with `supabase.AsyncClient` (`acreate_client`). This eliminates the threadpool entirely — all I/O becomes native asyncio with no socket contention.

The Supabase Python SDK (v2.0+) ships both clients side-by-side. The async API is a mirror of the sync one; method names and signatures are identical, they just return awaitables.

## Current Architecture

```
Browser ──► FastAPI (async) ──► sync dependency (threadpool) ──► sync repo ──► sync httpx/HTTP2
                                    ▲                                              │
                                    └── multiple threads share one TCP socket ─────┘
                                         (EAGAIN under concurrency)
```

### Key facts

| Component | Count | Current | Notes |
|---|---|---|---|
| Supabase client factory | 1 | `create_client()` → sync `Client` | `app/integrations/supabase_client.py` |
| Repository classes | 17 | All methods sync (`def`) | `app/repositories/`, `app/services/supabase_*.py` |
| Domain Protocol interfaces | 10 | All sync (`def`) | `app/domain/repositories.py` |
| Route handlers | 30+ | All sync (`def`) | `app/routes/*.py` (12 files) |
| Auth dependencies | 4 | All sync (`def`) | `app/dependencies.py` |
| Worker process | 1 | Async event loop, but calls sync repos | `app/worker_main.py` |

## Target Architecture

```
Browser ──► FastAPI (async) ──► async dependency ──► async repo ──► async httpx (native asyncio)
                                                                       │
                                                         one connection, no thread contention
```

## Migration Plan

The migration touches every layer from client creation to route handlers. It should be done in phases to keep each PR reviewable and independently deployable.

---

### Phase 1 — Async Client Factory + Dual Wiring

**Goal:** Create the async client alongside the sync one so both can coexist during migration.

**Files:**
- `app/integrations/supabase_client.py`

**Changes:**
```python
from supabase import AsyncClient, acreate_client

async def create_async_supabase_client(config: SupabaseConfig) -> AsyncClient:
    return await acreate_client(
        supabase_url=config.url,
        supabase_key=config.secret_key,
    )
```

- `app/main.py` (lifespan)

Wire the async client into `app.state.async_supabase_client` alongside the existing sync client. This lets repositories migrate one at a time.

**Deployable:** Yes — no behavior change, just adds the new client.

---

### Phase 2 — Migrate Auth Dependencies (Highest Impact)

**Goal:** Fix the exact code path that triggers the EAGAIN error.

**Files:**
- `app/services/supabase_auth_repository.py` — add async variants of `get_profile`, `upsert_profile`, etc.
- `app/dependencies.py` — convert `require_managed_auth`, `require_admin_managed_auth`, `require_signup_managed_auth` to `async def`

**Pattern for each repository method:**

```python
# Before (sync)
def get_profile(self, user_id: UUID | str) -> dict[str, Any] | None:
    resp = self._client.table(...).select("*").eq(...).limit(1).execute()
    ...

# After (async)
async def get_profile(self, user_id: UUID | str) -> dict[str, Any] | None:
    resp = await self._client.table(...).select("*").eq(...).limit(1).execute()
    ...
```

**Pattern for dependencies:**

```python
# Before
def require_managed_auth(request: Request, authorization: ...) -> AuthContext:
    ...
    profile = auth_repo.get_profile(user_id)

# After
async def require_managed_auth(request: Request, authorization: ...) -> AuthContext:
    ...
    profile = await auth_repo.get_profile(user_id)
```

FastAPI natively supports `async def` dependencies. No changes needed to the DI wiring.

**Note on `supabase_client.auth.get_user()`:** This call (line 69 in `dependencies.py`) uses the Supabase GoTrue auth client. The async Supabase client exposes an async auth client — change to `await supabase_client.auth.get_user(jwt=token)`.

**Deployable:** Yes — only auth paths change. Routes remain sync for now.

---

### Phase 3 — Migrate Domain Protocol Interfaces

**Goal:** Update the shared contracts so that async implementations satisfy them.

**Files:**
- `app/domain/repositories.py`

**Approach:** Define new async protocol variants alongside the existing sync ones. This avoids a flag-day change and lets implementations migrate incrementally.

```python
@runtime_checkable
class AsyncRunRepository(Protocol):
    async def get_job_run(self, id: str, owner_user_id: str) -> JobRun | None: ...
    async def save_job_run(self, run: JobRun) -> None: ...
    # ... mirror all methods from RunRepository
```

Once all implementations are async, remove the sync protocols and rename.

**Deployable:** Yes — protocol-only change, no runtime impact.

---

### Phase 4 — Migrate Postgres Repositories

**Goal:** Convert all 17 repository classes to use the async Supabase client.

**Files (each is one sub-PR):**
1. `app/repositories/postgres_repositories.py` — 13 repository classes (~60 methods)
2. `app/repositories/postgres_run_repository.py` — 1 class (~20 methods)
3. `app/repositories/supabase_beta_waitlist_repository.py` — 1 class
4. `app/services/supabase_auth_repository.py` — 1 class (started in Phase 2)
5. `app/services/supabase_queue_repository.py` — 1 class (queue operations)

**Mechanical change per method:**

```python
# Every self._client.table(...).execute() call becomes:
# await self._client.table(...).execute()
```

The Supabase async client's PostgREST builder has the same chaining API. The only difference is that `.execute()` returns an awaitable.

**Suggested sub-PR order:** Start with repositories used by the most-hit routes (`SupabaseAuthRepository` → `PostgresRunRepository` → remaining repositories in `postgres_repositories.py` → queue/waitlist).

**Deployable:** Each sub-PR is deployable if the corresponding route handlers are updated in the same PR (see Phase 5).

---

### Phase 5 — Convert Route Handlers to Async

**Goal:** Make all route handlers `async def` so they `await` repository calls directly on the event loop instead of running in the threadpool.

**Files:**
- `app/routes/auth_admin.py`
- `app/routes/auth_context.py`
- `app/routes/eula.py`
- `app/routes/invitations.py`
- `app/routes/locations.py`
- `app/routes/management.py`
- `app/routes/notion_oauth.py`
- `app/routes/public_waitlist.py`
- `app/routes/signup.py`
- `app/routes/test.py`
- `app/routes/ui_theme.py`

**Pattern:**

```python
# Before
@router.get("/runs")
def list_recent_runs_admin(request: Request, ctx: AuthContext = Depends(...)):
    run_repo = _run_repo_or_501(request)
    runs = run_repo.list_recent_job_runs(limit=limit, offset=offset)
    ...

# After
@router.get("/runs")
async def list_recent_runs_admin(request: Request, ctx: AuthContext = Depends(...)):
    run_repo = _run_repo_or_501(request)
    runs = await run_repo.list_recent_job_runs(limit=limit, offset=offset)
    ...
```

**Coordinate with Phase 4:** Each route file should be converted in the same PR as the repositories it depends on.

**Deployable:** Yes, per-route-file.

---

### Phase 6 — Migrate Worker Process

**Goal:** Replace blocking Supabase calls in the async worker loop with awaited async calls.

**Files:**
- `app/worker_main.py`
- `app/queue/worker.py`

The worker already runs an asyncio event loop. Currently it calls sync repository methods, which block the loop. After migration, these become `await` calls.

**Deployable:** Yes — independent from the API server changes.

---

### Phase 7 — Cleanup

**Goal:** Remove all sync Supabase artifacts.

**Changes:**
- Remove `create_supabase_client` (sync factory)
- Remove `app.state.supabase_client` (sync client)
- Remove sync Protocol interfaces from `app/domain/repositories.py`
- Rename async protocols to the canonical names
- Remove the `RequestIdCorsDebugMiddleware` and global exception handler added as interim fixes (or keep them if still useful)

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Async Supabase SDK has subtle API differences | Runtime errors | Write integration tests against a real Supabase instance for each migrated repository before deploying |
| Accidentally calling sync methods from async context | Blocks event loop | Add a linter rule or grep check in CI: no `def ` (sync) route handlers that call `.execute()` |
| Worker regression | Jobs stop processing | Deploy worker migration (Phase 6) separately from API migration; monitor queue depth |
| Mixed sync/async during transition | Confusing code, potential deadlocks | Keep sync and async clients co-existing via `app.state`; never mix sync client calls inside `async def` functions |
| PostgREST builder `.execute()` not awaitable on sync client | `TypeError` at runtime | Each PR must pair the async repository with the async client — never pass the sync client to an async repository |

## Estimating Scope

| Phase | Files | Method Signatures Changed | Complexity |
|---|---|---|---|
| 1 — Async client factory | 2 | 0 | Low |
| 2 — Auth dependencies | 2 | ~10 | Medium |
| 3 — Domain protocols | 1 | ~40 (new interfaces) | Low |
| 4 — Repositories | 5 | ~80 | Medium (mechanical) |
| 5 — Route handlers | 11 | ~35 | Medium (mechanical) |
| 6 — Worker | 2 | ~10 | Medium |
| 7 — Cleanup | 3 | Deletions | Low |
| **Total** | **~25 files** | **~175 changes** | |

## Alternative Considered: Disable HTTP/2

A simpler fix would be to force httpx to use HTTP/1.1 by passing `http2=False` to the underlying httpx client. This sidesteps the socket contention entirely because HTTP/1.1 uses separate connections per request.

**Pros:** One-line change, no async migration needed.
**Cons:** Does not fix the fundamental issue of blocking I/O in the async event loop. Every sync Supabase call still runs in the threadpool and holds a worker thread for the duration of the network round-trip. This limits concurrency to the threadpool size (default 40 in anyio) and adds latency from thread scheduling overhead.

The async migration is the correct long-term fix. The HTTP/2 disable is a valid stopgap if the migration timeline is long.
