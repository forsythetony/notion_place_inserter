# Architecture push: Global and per-user resource limits

This document turns the product brief below into an engineering design: **what exists today**, **what to add for beta**, **where to enforce**, and **how metering interacts** with cost tracking elsewhere.

---

## Product / architecture brief

One pretty important feature is enforcing both global limits and user-specific limits on things like:

* the number of steps within a pipeline
* the number of pipelines within a stage
* the number of stages within a job
* the number of jobs that a user is able to create
* the number of triggers that a user is able to create

There should be a two-layered resolution system here. I should be able, as the admin, to set global limits on everything and maybe an admin configuration pane somewhere. The user: I should be able to set limits on a per-user basis. Maybe we start out with giving all users a certain amount, a certain limit on things. For the moment this is just to keep the beta testing bounded. I don't want to have situations where a beta tester jumps in and they create a pipeline with a thousand steps. That becomes a bottleneck in our system where it crashes one of the nodes. I want to keep it bounded on purpose and kind of open that up gradually as I move forward. I want to be able to control it both on a global level and on a user level. In the future this could also evolve into different tiers of user support or different tiers of plans for users. You may be hitting up a limit on the free plan, which gives you maybe ten jobs that you can create and a maximum of five triggers. By upgrading to Pro you can unlock more.

Oh another important configuration value on the user would be the number of max daily pipeline runs. This would probably happen at the scheduling stage where the user hits the trigger and the trigger goes to enqueue a job. Before enqueuing the job it would first check the table to see how many runs this user has used this month and what is their daily maximum for the month. And we could do this both on a daily basis and a monthly basis.

---

## Current implementation (codebase)

### Structural graph limits (stages / pipelines / steps)

| Concern | Domain / storage | Enforcement | Defaults |
|--------|-------------------|-------------|----------|
| `max_stages_per_job` | `AppLimits` in `app/domain/limits.py` | `ValidationService.validate_job_graph` in `app/services/validation_service.py` | YAML: `yaml_loader.parse_app_limits`; Postgres: `app/repositories/postgres_repositories.py` (`PostgresAppConfigRepository`) |
| `max_pipelines_per_stage` | same | same | same |
| `max_steps_per_pipeline` | same | same | same |

**Resolution order today:** `PostgresAppConfigRepository.get_by_owner` loads the **per-owner** row first; if missing, it falls back to the **global** row (`owner_user_id IS NULL`). There is **no** `min(global, user)` merge: whichever single row applies is used. The dataclass has only the three integers above—no job count, trigger count, or run quotas.

**Schema:** `app_limits` in `supabase/migrations/20260315100000_phase4_pr01_datastore_schema.sql` — one row per user **or** one platform default row (`owner_user_id` nullable, unique partial index for the global row). RLS: users may **SELECT** own row or global row; **INSERT/UPDATE/DELETE** only on **own** row (global row is not user-writable).

**API surface for UI:** `GET /management/account` (`app/routes/management.py`) includes a `limits` object when `app_config_repository` returns values—used by the editor (e.g. `max_steps_per_pipeline` for “Add step” affordances).

### Inventory limits (jobs, triggers)

**Not implemented** as centralized limits. Counts would be derived from `job_definitions`, `trigger_definitions` (and related link tables) per `owner_user_id`, compared against caps to be added.

### Throughput limits (runs per day / month)

**Not implemented.** The enqueue path (`app/routes/locations.py` async branch, and `enqueue_pipeline_live_test_run` in `app/routes/management.py`) creates a `job_run` and sends to `pgmq` **without** a pre-check against run volume.

**Related but distinct:** `usage_records` (`app/domain/runs.py`, `UsageRecord`) records **LLM tokens and external API usage** via `UsageAccountingService`—suitable for **cost** attribution, not the same as **run quota** metering. Run counts for quotas should key off `job_runs` (status and `created_at`) or a dedicated counter table (see below).

---

## Limit taxonomy

Useful to split work so enforcement and storage stay consistent:

1. **Structural limits** — Bound graph size (already partially done). Prevents oversized definitions from hitting worker memory, validation cost, and UI performance.
2. **Inventory limits** — Max entities per owner (jobs, triggers, connectors, etc.). Enforced at **create** time (and optionally on import/clone).
3. **Throughput limits** — Max pipeline/job runs per calendar day / rolling window / month. Enforced at **enqueue** time (and optionally a second check at worker dequeue for defense in depth).

---

## Target resolution order (global vs user vs future tiers)

For **maximum allowed** style caps (all of the above), a predictable rule for beta is:

**`effective = min(global_ceiling, user_ceiling)`** when both exist, where each ceiling is the maximum allowed for that dimension.

- **Global row** (`owner_user_id IS NULL`): platform-wide ceiling; admin-only mutation (service role or dedicated admin API), not RLS user-writable.
- **Per-user row** (`owner_user_id = uuid`): optional override; if absent, inherit global for that dimension only if you define “inherit” per field, **or** treat missing user row as “use global only.”

**Future tiers (Pro / Free):** encode as either:

- **Option A:** Tier sets **default** per-user row template on signup / tier change; still merge with global via `min`, or  
- **Option B:** Tier stores multipliers or absolute caps in a `plan_tiers` table; `effective = min(global, tier_cap, admin_per_user_override)`.

Pick one model before building billing UX; Option A matches the current “row per user” shape with minimal new concepts.

---

## Storage model

### Extend `app_limits` (structural + inventory)

Add nullable or non-null columns with CHECK constraints, e.g.:

- `max_jobs_per_owner`, `max_triggers_per_owner` (inventory)
- Optionally `max_linked_pipelines_per_trigger` if product needs it

Keep **global** and **per-user** rows as today; implement **merge in application code** when loading effective limits (repository or small `EffectiveLimits` service), not only “first user row else global.”

### Run quotas (throughput)

**Option 1 — Derive from `job_runs`:**  
`COUNT(*)` for `owner_user_id` and `created_at` in `[start_of_day, end_of_day)` (and similarly for month). Simple, auditable; needs **indexes** on `(owner_user_id, created_at)` if not already present. **Race:** two concurrent enqueues can both pass a count check unless the increment is atomic with the check (see below).

**Option 2 — Counter table** (`user_run_usage` or generic `usage_counters`):  
Rows keyed by `owner_user_id`, `period` (`day` / `month`), `period_start` (date), `count`. Enforce with a **single transaction**: `SELECT … FOR UPDATE` or `INSERT … ON CONFLICT DO UPDATE` with `RETURNING count` and compare to cap. Matches common DB-backed rate limit patterns (fixed/sliding windows with transactional integrity).

**Option 3 — Redis / external** (later): Higher QPS token buckets; still persist periodically or use for soft limits only until beta scale demands it.

For **beta**, Option 1 or 2 in Postgres is enough; align with horizontal worker scaling docs so all API instances share the same source of truth.

### Admin configuration

- **Service role** or **admin-only routes** to upsert global `app_limits` and per-user overrides (RLS today prevents users from editing the global row).
- UI: admin panel section listing effective limits per user (read from merged computation).

---

## Enforcement points

| Limit type | Primary enforcement | Secondary / UX |
|------------|---------------------|----------------|
| Structural (stages / pipelines / steps) | `ValidationService` on save (already) | Editor: disable add step / show max from `GET /management/account` (already partial) |
| Inventory (jobs, triggers) | Create/update routes for definitions **before** commit | List views can show “X of Y used” |
| Run quotas | **Before** `run_repo.create_job` + `queue_repo.send` in enqueue paths | Return **429** or **403** with structured body `{ "code": "run_quota_exceeded", "period": "day", "limit": N, "used": M }` |

**Important:** Enqueue-time enforcement must be **atomic** with queueing: either transactional counter increment + cap check, or `INSERT job_run` with a deferred constraint / unique partial index pattern—otherwise double-submit can exceed caps.

**Worker:** Optional second check on dequeue reduces abuse if something bypasses the API; queue message should carry `owner_user_id` for logging and policy.

---

## Metering: daily vs monthly

- **Calendar day / month** — Easiest for users to understand (“500 runs per month”). Align `period_start` to UTC or tenant timezone (document the choice; beta can use UTC).
- **Rolling 30-day window** — Smoother; implementation is a sliding window counter or sum over `job_runs` for last 30 days; more expensive at query time unless pre-aggregated.

Product copy in the brief mentions both “daily maximum for the month” and daily/monthly—**decide explicitly** whether monthly is a separate cap, a sum of daily caps, or one monthly pool.

---

## External patterns (research summary)

Production APIs usually combine:

- **Central counters** for distributed API workers (avoid per-process memory counts).
- **Transactional increments** in Postgres: `INSERT … ON CONFLICT`, or **advisory locks** per user key to serialize increments in a window (common pattern in Postgres rate-limit writeups, e.g. Neon’s guides on rate limiting in Postgres).
- **Token bucket / sliding window** semantics for smooth throughput; **fixed windows** for simple billing-aligned quotas.

Redis appears often as a **fast path** at scale; for bounded beta traffic, Postgres-only is acceptable if indexes and transaction scope are correct.

---

## Phasing (suggested)

1. **Beta-minimum:** Merge `min(global, user)` for existing three structural fields; add **inventory** caps for jobs + triggers; add **daily** run cap from `job_runs` or counter table on enqueue paths used by beta testers.
2. **Next:** Monthly run cap; admin UI; structured error codes; metrics/alerts when users approach limits.
3. **Later:** Tiered plans, rolling windows, Redis if needed.

---

## Open decisions

- Timezone for calendar buckets (UTC vs user profile).
- Whether **failed** runs count toward quota (often yes for enqueue attempts; sometimes only `completed` runs—product choice).
- Whether **live test** enqueue (`management` routes) shares the same quota as production triggers or a separate smaller cap.

---

## Related docs

- [`runtime-architecture-onboarding.md`](../phase-4-datastore-backed-definitions/runtime-architecture-onboarding.md) — datastore tables including `app_limits`, `usage_records`, `job_runs`.
- [`enhanced-user-monitoring-and-cost-tracking.md`](./enhanced-user-monitoring-and-cost-tracking.md) — cost attribution vs run quotas (complementary).
- [`worker-horizontal-scaling-and-queue-coordination.md`](./worker-horizontal-scaling-and-queue-coordination.md) — why enqueue limits must be DB-coherent across workers/API instances.
