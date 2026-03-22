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

### Three admin configuration sources (do not conflate)

1. **Global limits** — Admin-configured **platform ceilings** for each dimension (including run counts: daily, monthly, structural caps, inventory caps, etc.). This row is the **safeguard**: no user can exceed what global allows, even if their per-user row says otherwise. **Used on every enforcement path** once limits are loaded.

2. **Default run counts** (and, by extension, **default limits** for other dimensions if we seed them the same way) — A **separate** admin configuration: values applied **only when a new user is created**, typically by copying into that user’s `app_limits` row (or equivalent). This template is **not** consulted during runtime “what is the effective limit?” resolution. After creation, only the **user row** and **global row** matter for checks.

3. **Per-user limits** — Stored on the user’s own row (`owner_user_id = uuid`). Optional overrides per dimension; admin-editable via the users admin UI/API.

### Runtime resolution algorithm (per dimension)

When computing the **effective ceiling** used for enforcement (validation, enqueue quota, etc.):

1. **Read the user’s configuration** for that dimension (per-user row / stored fields).
2. **If the user has configured values** for that dimension (non-null / explicitly set—define “configured” consistently in code, e.g. not “missing row” vs “row present with nulls”), **use those values** as the **user candidate** for that dimension.
3. **If the user does not have configured values** for that dimension, **use the global values** for that dimension as the user candidate (inherit global into the user side of the comparison).
4. **If neither global nor user provides a value** for that dimension (both unset / unknown), **fail with an error** — the system cannot enforce a limit it does not know. This should be rare if global limits are required to be configured for production.

Then apply the **global safeguard** (platform ceiling):

- **`effective_ceiling = min(global_limit, user_candidate)`** for that dimension.

So: global is always the **backstop**. If global is **lower** than what the per-user row would allow, **global wins**. The **default run counts** configuration does **not** participate in this layered check—only **global** and **user** rows (after user creation) do.

### Observability (tracing)

Whenever limits are resolved for a request or background job, **log enough to trace the decision**, for example:

- **User identity** (`owner_user_id` / subject).
- **Which dimensions** were resolved and for what operation (e.g. enqueue, graph save).
- **Raw inputs:** identifiers or snapshots of the **global** row and **per-user** row (or hashes/versions if rows are large), and which fields were treated as “user configured” vs inherited.
- **Intermediate values:** `user_candidate` per dimension, `global_limit` per dimension.
- **Outputs:** final **effective_ceiling** per dimension, or **error** with reason when resolution fails (e.g. missing global and user).

Use structured logging so support and on-call can follow **why** a user hit or did not hit a cap.

### Future tiers / billing (out of scope for beta)

**No decision required for beta.** Paid tiers, plan SKUs, and user billing are **deferred** until we have more research on **what these runs cost** (and related unit economics). When we approach billing UX, revisit how tiers interact with limits—for example:

- **Option A:** Tier adjusts **default** values at signup / tier change (similar to “default run counts”), plus per-user overrides; still apply **global safeguard** via `min(global, user_candidate)` at runtime.  
- **Option B:** Tier stores caps in a `plan_tiers` table; `effective = min(global, tier_cap, user_candidate)` if we need a third layer.

Until then, **global limits + default run counts (new users) + per-user overrides + safeguard** are enough.

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

Admin-facing configuration falls into three buckets (see **Target resolution order** above):

- **Global limits** — Platform-wide ceilings (including run counts); mandatory for safe operation; enforce **safeguard** `min(global, user_candidate)` at runtime.
- **Default run counts** (defaults for other limit dimensions if desired) — Used **only** when **creating** a new user (seed the user’s row). **Not** read during enforcement resolution.
- **Per-user overrides** — Edits to a specific user’s row after creation.

Implementation detail: **Service role** or **admin-only routes** to upsert global rows, default-for-new-user templates, and per-user rows (RLS today prevents non-admins from editing the global row).

#### Admin users API and UI (tabbed admin surface)

**API — implement / extend**

- **Surface limits on the existing admin users API** — the same backend surface that powers the tabbed admin experience (**Users**, **Invites**, **Cohorts**, and related user metadata). Responses for a given user should include what admins need to reason about limits, for example:
  - **Effective limits** per dimension (after **user candidate** resolution and **`min(global, user_candidate)`** safeguard; see **Target resolution order**).
  - **Per-user stored values** vs **global** vs **effective** (so admins see what was configured on the user row vs what actually applies).
  - **Usage vs cap** where cheap to provide (e.g. queued runs today / this month in UTC, counts of jobs/triggers vs caps) so support can see “X of Y” without a separate tool.
- **Mutations:** upsert of per-user limit overrides and (where exposed) global defaults should remain **admin-authenticated** only; align with RLS and service-role patterns already used for admin operations.

**UI — desired behavior**

- On the **Users** tab (within the same tabbed admin shell as user info, invites, cohorts): each **user row** should offer **Edit** and/or **Info** (or a single entry point) that opens **more detail** for that user.
- That detail view (drawer, modal, or slide-over—implementation choice) must include a dedicated **Limits** section: show effective caps, usage vs limits where available, and controls or inline edit for admin-tunable overrides consistent with the API above.
- **Global limits** and **default run counts** (new-user seeding) should be manageable from dedicated admin settings UIs; the per-user **Users** tab detail focuses on **per-user** visibility and overrides. Defaults-for-new-users are **not** shown as part of runtime “effective limit” resolution—only global + user row.

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

- **Calendar day / month — timezone (decided):** Use **UTC** for day/month bucket boundaries (not per-user profile timezone). When implementing counters or queries, align `period_start` / window boundaries to UTC.
- **Daily vs monthly — relationship (decided):** They are **separate caps**, evaluated independently. A user must satisfy **both** when both are configured (e.g. under daily and under monthly for the current periods).
- **Daily cap — purpose (beta):** The primary intent is **load protection** while the product and infrastructure are still maturing: limit how hard a user can hit the service in a single day so beta traffic does not overwhelm capacity. **Limits should be admin-configurable** so we can **raise** them if users legitimately run into them too often without changing code.
- **Monthly cap** — Broader budget over a calendar month (UTC); not derived from the daily cap (not “sum of dailies” or a single pool that replaces both). Product/billing can still use different monthly semantics later; for beta, treat **daily** and **monthly** as two independent knobs.
- **Rolling 30-day window** (optional later) — Smoother than calendar month for some products; implementation is a sliding window counter or sum over `job_runs` for last 30 days; more expensive at query time unless pre-aggregated. Distinct from the two calendar caps above if we ever add it.

### Run quota semantics (decided for beta)

- **What counts:** A run counts toward quota when it is **successfully queued** (same moment we create a `job_runs` row with `status` queued). Refining later so users are not charged for failures or no-op runs is acceptable but **not** required for the first enforcement pass.
- **Editor live test:** `POST /management/pipelines/{pipeline_id}/run` **does not** consume per-user production run quota. `job_runs` (and queue messages) are still recorded for observability and abuse review; **do not** apply the user quota check on this path for now.

---

## External patterns (research summary)

Production APIs usually combine:

- **Central counters** for distributed API workers (avoid per-process memory counts).
- **Transactional increments** in Postgres: `INSERT … ON CONFLICT`, or **advisory locks** per user key to serialize increments in a window (common pattern in Postgres rate-limit writeups, e.g. Neon’s guides on rate limiting in Postgres).
- **Token bucket / sliding window** semantics for smooth throughput; **fixed windows** for simple billing-aligned quotas.

Redis appears often as a **fast path** at scale; for bounded beta traffic, Postgres-only is acceptable if indexes and transaction scope are correct.

---

## Phasing (suggested)

1. **Beta-minimum:** Implement resolution (**user candidate** from per-user row else global, then **`min(global, user_candidate)`**), **default run counts** seeding on user creation, and **tracing logs**; apply to existing three structural fields; add **inventory** caps for jobs + triggers; add **daily** run cap from `job_runs` or counter table on enqueue paths used by beta testers.
2. **Next:** Monthly run cap; **admin users API + Users tab UI** (per-user detail with **Limits** section; see “Admin configuration”); structured error codes; metrics/alerts when users approach limits.
3. **Later:** Billing / tiered plans (after cost research); rolling windows; Redis if needed.

---

## Resolved decisions (beta)

- **Timezone for calendar buckets:** **UTC** (see “Metering” above).
- **Daily vs monthly:** **Separate caps** (both may apply). Daily is primarily **burst / load protection** and **tunable** by admins without deploys; see “Metering” above.
- **What counts toward quota:** Any **successfully queued** run (initial policy: count at enqueue). Room to tighten later so users are not charged for runs that do nothing.
- **Live test vs production:** Editor live-test enqueue **does not** apply the user run quota; runs are still stored for monitoring and abuse detection. Quota enforcement targets production-style enqueue (e.g. `locations` trigger path), not `management` live-test run.
- **Admin sources:** **Global limits** (safeguard), **default run counts** (seed new users only—not used in runtime layered check), **per-user** row. Resolution: user candidate from user config else global; then **`effective = min(global, user_candidate)`**; **error** if a dimension has no global or user value; **structured logging** on resolution (see **Target resolution order**).
- **Tiers / billing:** **Deferred** (not required for beta); pick Option A vs B (or another shape) only when building billing, after cost research (see **Future tiers / billing**).

---

## Related docs

- [`runtime-architecture-onboarding.md`](../phase-4-datastore-backed-definitions/runtime-architecture-onboarding.md) — datastore tables including `app_limits`, `usage_records`, `job_runs`.
- [`enhanced-user-monitoring-and-cost-tracking.md`](./enhanced-user-monitoring-and-cost-tracking.md) — cost attribution vs run quotas (complementary).
- [`worker-horizontal-scaling-and-queue-coordination.md`](./worker-horizontal-scaling-and-queue-coordination.md) — why enqueue limits must be DB-coherent across workers/API instances.
