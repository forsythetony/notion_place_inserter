# Architecture push: Enhanced user monitoring and cost tracking

**Status:** **Open** — implementation not started. **Review:** Ready for review (no human sign-off recorded in [`work-log.md`](../../work-log.md)).

---

## Product / architecture brief

The next and potentially most important part is **enhanced user monitoring**. When a user runs a pipeline, operators need a trustworthy picture of **activity** and **spend drivers**: how often they run work, which external capabilities each run exercises, and how much measurable usage (tokens, API calls) accumulates—eventually mapped to **estimated cost** for beta economics and capacity planning.

Concrete questions this work should answer for a given user (and optionally a time window):

* **Activity** — Active in the last week? How many **job / pipeline runs**? How many times did a given **trigger** fire (runs attributed to that trigger)?
* **LLM** — How many **tokens** were consumed via Anthropic (and later other providers), broken down by model where possible?
* **External APIs** — How many calls to **Google Places** (and field/SKU granularity later), **Freepik Icons API** (icon search; billable per [Freepik’s plan](https://www.freepik.com/api)), **Notion**, and other integrations?
* **Cost** — Not only raw counts: **estimated currency cost** when rate cards exist (per provider pricing model: tokens vs per-call SKUs, etc.).

Different APIs price differently: e.g. Google Places may vary by **Places API product and requested fields**; Claude-style models by **input/output tokens**. The **end state** is: pick a user → see activity, run volume, trigger attribution, token totals, per-provider call counts, and **estimated spend**—so we can reason about typical user patterns and beta burn rate.

---

## Related documents

| Topic | Doc |
|--------|-----|
| Run quotas vs usage/cost | [`global-and-per-user-resource-limits.md`](./global-and-per-user-resource-limits.md) — throughput limits (daily/monthly runs) are **enforcement**; `usage_records` here are **attribution** and cost signals. |
| Logging, metrics, tracing direction | [`error-handling-observability-and-telemetry.md`](./error-handling-observability-and-telemetry.md) — platform observability (OTEL, structured logs) complements **product** usage/cost views. |
| Historical usage design (Phase 3) | [`p3_pr08-runs-usage-observability-and-docs.md`](../phase-3-yaml-backed-product-model/p3_pr08-runs-usage-observability-and-docs.md) — introduced `UsageAccountingService` and YAML usage files. |
| Domain model | [`app/domain/runs.py`](../../../../app/domain/runs.py) — `UsageRecord`, `JobRun`, `StepRun`, etc. |
| Run persistence (Postgres) | [`app/repositories/postgres_run_repository.py`](../../../../app/repositories/postgres_run_repository.py) — `list_job_runs_by_owner`, `list_step_runs_for_job_run`, `save_usage_record`, etc. |

---

## Current implementation (codebase)

### Data model: `UsageRecord`

`UsageRecord` (`app/domain/runs.py`) is the unit of persisted usage:

* `usage_type`: e.g. `llm_tokens`, `external_api_call`
* `provider`: e.g. `anthropic`, `google_places`, `freepik`
* `metric_name` / `metric_value`: for LLM usage, `metric_name` is `total_tokens` and `metric_value` is prompt+completion sum; for external APIs, `metric_value` is typically **1** per call (count), with `metric_name` carrying the **operation** (e.g. Places operation)
* `owner_user_id`, `job_run_id`, optional `step_run_id`
* `metadata`: e.g. for LLM: `prompt_tokens`, `completion_tokens`, `model`

Rows land in Postgres table **`usage_records`** (Phase 4 schema); persistence goes through `PostgresRunRepository.save_usage_record` (and YAML path historically in Phase 3).

### Service: `UsageAccountingService`

[`app/services/usage_accounting_service.py`](../../../../app/services/usage_accounting_service.py) exposes:

* `record_llm_tokens(...)` — persists one `UsageRecord` per invocation site; failures are logged (`usage_accounting_save_llm_tokens_failed`) and do not fail the step.
* `record_external_api_call(...)` — one row per logical external call (`metric_value=1`), with `provider`, `operation`, optional `metadata`.

`JobExecutionService` injects this as `ctx` service `usage_accounting` when a run repository is available.

### Target pattern: generic usage objects at API call sites

The **end state** for coverage is that **every outbound API** (handler, client wrapper, or thin service used from step runtime) follows the same mental model:

1. **Do the work** — resolve inputs, optionally build request, **perform the call**, collect the response (or error).
2. **Construct a single, general usage payload** — not vendor-specific logic spread across the repo, but a small structured description of *what was consumed*, for example:
   * **Units consumed** — a numeric **amount** (e.g. token total, `1` for one logical HTTP/API operation, future: SKU-weighted units).
   * **Unit kind** — what that amount means: e.g. `llm_tokens`, `external_api_call`, or a future enum that rate cards understand.
   * **Provider** — who bills us: `anthropic`, `google_places`, `freepik`, `notion`, etc.
   * **API / operation name** — logical name for aggregation and rate cards (e.g. Places `search_places`, Freepik `search_icons`); maps cleanly to today’s `metric_name` for external calls or LLM naming.
   * **Linkage** — **`job_run_id`**, **`owner_user_id`**, **`step_run_id`** (when in a step) so usage joins to runs, admin explorer, and per-step drill-down.
   * **Extra context** — optional **`metadata`** (model name, input/output token split, field masks, HTTP status, idempotency keys) for debugging and **richer rate cards**, without bloating the core columns.

3. **Persist via the usage service** — call into **`UsageAccountingService`** (or a future unified entry point such as `record_usage(...)`) so the payload is validated and written as one **`UsageRecord`** row (same Postgres `usage_records` table). Failures should **log and never fail the step**, matching current `record_*` behavior.

Today’s codebase uses **specialized helpers** (`record_llm_tokens`, `record_external_api_call`) that *are* this pattern in thin form; a unified **dataclass or typed “usage event”** passed to a single persist method would reduce drift and make new integrations (Freepik, Notion, etc.) copy-paste-safe. The persisted row remains **`UsageRecord`**-shaped so aggregation, admin APIs, and rate cards stay stable.

**Boundaries:** Construct usage **at the call site** (or immediately inside a dedicated client after the HTTP/SDK returns) so manual overrides / dry-run paths can **skip** persistence when no real vendor call occurred. Do not infer usage only from logs.

### Worked example: Generic Book Service (per word returned)

Imagine onboarding **genericbookservice.com**: you `GET` a summary, and the vendor bills the platform **by the number of words they return** (not per HTTP call).

* The **API response** includes something like `words_returned: 2000` (or the client counts words from the body—product decision per integration).
* At the call site you build the usage payload with:
  * **Units consumed:** `2000`
  * **Unit kind:** **`word`** (or a stable string such as `words_returned`) so rate cards know how to price it—e.g. **$/1k words** or **$/word**.
  * **Provider:** a stable id such as **`generic_book_service`** (the “provider enum” / string stored on every `usage_records` row for that vendor).
  * **API / operation name:** e.g. `fetch_summary` or `get_book_excerpt`—whatever you need to distinguish endpoints if pricing differs.
  * **Linkage:** `job_run_id`, `owner_user_id`, `step_run_id` as usual.
  * **Metadata:** optional raw vendor fields, request id, language, etc.

Persist one **`UsageRecord`** row (or one row per logical billable response—align with the vendor’s invoice line). Today’s schema uses **`metric_value`** for the numeric amount and **`metric_name`** / **`usage_type`** to interpret it; a per-word integration might use `usage_type` + `metric_name` such that aggregations sum **words** correctly (exact column mapping is an implementation detail as long as **aggregation and rate cards share one definition**).

### Provider / integration registry (admin onboarding, target)

To avoid hardcoding every new vendor only in Python, support an **operator-facing onboarding flow** (admin UI + API) when adding an integration such as Generic Book Service:

| Captured in UI (example) | Purpose |
|--------------------------|--------|
| **Provider id** (stable key) | Matches `usage_records.provider` and code (e.g. `generic_book_service`). Treat as the canonical **enum** value for this vendor. |
| **Display name** | Human label in admin dashboards (e.g. “Generic Book Service”). |
| **Short description** | What the integration does; helps operators and future docs. |
| **Billing unit** | What one unit of `metric_value` means for this provider in the common case (e.g. `word`, `call`, `token`)—drives **default rate-card dimensions** and UI copy (“2,000 words this run”). |
| **Optional notes** | Link to vendor pricing page, internal owner, etc. |

**Persistence:** Store rows in **Postgres** (dedicated table such as `usage_provider_definitions`, or validated JSON behind an admin API). **Rate cards** and the **admin run explorer** resolve **`provider` + unit semantics** through this registry so new vendors do not require a migration just to show a label—only when you add new **pricing** rules.

Runtime code still **emits usage** at call sites; the registry is **metadata** for operators, reporting, and consistent labeling—not a substitute for recording each API consumption event.

### Bootstrapping built-in providers (YAML catalog + upsert)

First-party integrations we already ship (**Google Places**, **Freepik**, **Anthropic (Claude)**, **Notion**, etc.) should not rely on a human clicking through the admin UI before the registry is usable. Treat them like other **catalog data**: define a **version-controlled YAML file** (alongside the product model / bootstrap pattern used elsewhere—see [`postgres_seed_service`](../../../../app/services/postgres_seed_service.py) and YAML under `product_model/`) that lists each **known provider** with at least:

* **provider id** — must match `usage_records.provider` and runtime strings (e.g. `google_places`, `freepik`, `anthropic`, `notion`).
* **display name** and **short description** — for admin and docs.
* **Primary billing / charge semantics** — e.g. “per HTTP call”, “per token”, “per returned word” (free text or a small enum for UI and rate-card defaults).
* **Default unit label** — aligns with [Provider registry](#provider--integration-registry-admin-onboarding-target) (e.g. `call`, `token`, `word`) so rollups and copy stay consistent.

**Load strategy:** On **deploy, migrate, or seed** (same phases as other bootstrap data), **parse the YAML**, validate schema, and **upsert** into the provider table by **`provider_id`**. If a row already exists (e.g. operator-edited description), policy can be **merge**: YAML supplies defaults for missing columns, or **overwrite** catalog fields only on explicit seed runs—pick one rule and document it in the seed runbook.

**Why YAML + DB:** Git remains the **source of truth for “what we ship”**; Postgres is the **queryable runtime** for the admin UI and joins. New environments get correct rows without manual steps; **admin-created** providers (Generic Book Service, etc.) still live in DB and may be **out-of-band** from YAML until promoted to catalog files if desired.

### Where usage is recorded today

| Handler / area | What is recorded |
|----------------|------------------|
| `ai_prompt` | LLM tokens via `claude.get_last_usage()` → `record_llm_tokens` (`anthropic`) |
| `optimize_input` | Same pattern |
| `google_places_lookup` | `record_external_api_call` for Google Places operations (see handler for `provider` / `operation` / metadata) |

### Freepik Icons API — usage attribution (**planned**, not in runtime yet)

**Why it matters:** The **Freepik Icons API** (`SearchIconsHandler` / [`FreepikService`](../../../../app/services/freepik_service.py)) is a **paid third-party** dependency (`FREEPIK_API_KEY`). Each icon search issues HTTP to Freepik; that usage **drives platform cost** and must be visible in **`usage_records`** so the [admin run explorer](#admin-run-explorer-per-user) and rate-card math include it alongside Google Places and Anthropic.

**Intended implementation (for a future coverage ticket):** After a real API attempt (not a live-test **manual override**), call `UsageAccountingService.record_external_api_call` with `provider` = **`freepik`**, `operation` = **`search_icons`**, plus `job_run_id`, `owner_user_id`, and `step_run_id` when present. Do not record when the resolved query is empty (no request). Align with the pattern used in [`google_places_lookup`](../../../../app/services/job_execution/handlers/google_places_lookup.py).

**Documentation-only workflow note:** A short-lived change added this recording in `SearchIconsHandler` and was **reverted** so the team could keep an architecture pass **doc-first** without shipping runtime behavior in the same session. The **rationale above** stands; wire-up belongs in implementation work with unit tests and (if needed) a work-log entry.

**Gaps (as of this writing):**

* **Freepik (`search_icons`)** — does **not** yet write `usage_records`; required for accurate operator cost views—see [Freepik Icons API — usage attribution](#freepik-icons-api--usage-attribution-planned-not-in-runtime-yet).
* **Notion** (and other integrations) may not emit `usage_records` for every API touchpoint—confirm per handler and add `record_external_api_call` (or a dedicated `usage_type`) where billable or capacity-relevant.
* **No unified “trigger fired count”** beyond inferring from **`job_runs`** rows (each run carries `trigger_id`)—see below.
* **No dollar amounts** in DB—only raw usage suitable for **later** multiplication by rate cards.

---

## Design: usage dimensions and attribution

### Dimensions operators care about

1. **Who** — `owner_user_id` (tenant/user scope for beta).
2. **When** — `started_at` / `completed_at` on `job_runs` and timestamps on usage rows (ensure usage records are queryable by time; if only `job_run` time exists, join `usage_records` → `job_runs` for windowing).
3. **What run** — `job_run_id`, and optionally `step_run_id` for step-level drill-down.
4. **What capability** — `usage_type`, `provider`, `metric_name` / `operation`, and LLM `metadata.model`.
5. **Trigger** — `JobRun.trigger_id` links a run to a trigger definition; **counting “trigger fires”** = count runs (or successful runs) grouped by `trigger_id` over a window.

### Activity summary (without new event types)

For “active last week” and “pipeline runs”:

* Query **`job_runs`** filtered by `owner_user_id` and `started_at`/`created_at` in range, with optional status filter (e.g. exclude `cancelled` if defined).
* **Pipeline run** counts may align 1:1 with job runs for single-pipeline jobs, or require joining **`pipeline_run_executions`** if you need per-pipeline granularity—product language should match what the UI shows (“job run” vs “pipeline run”).

### Cost estimation (estimated USD or internal credits)

Keep **pricing out of hot path** execution: store **raw usage** first; apply **rate cards** in batch or read-time aggregation.

**Suggested approach:**

1. **Versioned rate card** configuration (admin-editable later), e.g. JSON or table rows keyed by `(provider, usage_type, model | operation | sku_id)` with **effective date ranges** so list prices can change.
2. **LLM** — Map `(model, input_tokens, output_tokens)` to vendor list or internal **$/1M tokens** for input vs output (Anthropic publishes token pricing per model).
3. **Google Places** — Map `(operation, metadata.sku or field mask)` to per-call or per-SKU cost; pricing is product-specific (Places API New vs Legacy, etc.)—**online vendor docs** should be the source of truth when implementing, not hardcoded guesses in this doc.
4. **Freepik** — When **`search_icons`** emits usage (see [Freepik section](#freepik-icons-api--usage-attribution-planned-not-in-runtime-yet)), map `search_icons` (per-call) to Freepik API plan pricing; raw **`usage_records`** should use `provider=freepik`, `metric_name=search_icons`.
5. **Notion** — If/when metering is added, align with Notion’s billing model for the integration surface you use.

Output artifacts:

* **Estimated cost per `usage_record` row** (optional stored column populated by nightly job), or **computed only in aggregate queries**.
* **Rollups**: per user per day / per month: `sum(estimated_cost)`, `sum(tokens)`, `sum(api_calls)` by provider.

---

## Storage and aggregation

| Layer | Purpose |
|-------|--------|
| **Raw** | `usage_records` + `job_runs` (+ `step_runs` if step-level traces matter) — source of truth. |
| **Rollups** (optional but recommended for admin UI) | Periodic job or materialized view: `user_id`, `day`, `provider`, `usage_type`, `metric_key`, `sum(metric_value)`, `sum(estimated_cost)`. |
| **Provider registry** (target) | Admin-defined **provider id**, display name, billing unit, description — see [Provider / integration registry](#provider--integration-registry-admin-onboarding-target); **built-in rows** seeded from version-controlled YAML — see [Bootstrapping built-in providers](#bootstrapping-built-in-providers-yaml-catalog--upsert); joins to raw usage for labels and default rate-card keys. |
| **Rate cards** | Small config table or JSON blob with schema validation; avoid scattering magic numbers in Python. |

**Query patterns:** Admin API endpoints (future) should accept `user_id`, `from`, `to`, and return both **tables** (CSV export later) and **summary cards** (totals, top providers, top triggers by run count).

---

## Admin run explorer (per user)

Operators need a **single place** (admin UI, backed by admin APIs) to inspect **all job runs for a chosen end user** and answer: when did it run, what shape did execution take (stages / pipelines / steps), what did it cost in third-party terms, and where is the **per-step product log** for debugging.

This is **product/operator analytics** on persisted run data—not live platform traces (see [`error-handling-observability-and-telemetry.md`](./error-handling-observability-and-telemetry.md)).

### What the admin should see

| Operator need | Source of truth (Postgres) | Notes |
|----------------|----------------------------|--------|
| **When the run happened** | `job_runs` | Prefer **`created_at`** (enqueue / record creation) and **`started_at` / `completed_at`** (execution window) for display and sorting. Domain `JobRun` today surfaces start/complete; expose DB `created_at` in admin payloads if not already mapped. |
| **Dig into logging for that run** | `step_runs` | Each row has **`processing_log`** (string lines, chronological), plus **`input_summary`**, **`output_summary`**, **`error_summary`**, **`step_template_id`**, **`pipeline_id`** (via join from `pipeline_run_executions`). `PostgresRunRepository.list_step_runs_for_job_run` already loads step rows for a job run + owner; admin path should reuse or mirror this with **service role** and **admin auth**. |
| **How many pipelines** | `pipeline_run_executions` | **Count** rows where `job_run_id` = the run (one row per pipeline execution within the job graph). |
| **How many steps** | `step_runs` | **Count** rows where `job_run_id` = the run. |
| **How many stages** | `stage_runs` | **Count** rows where `job_run_id` = the run. |
| **Cost of the run (estimated)** | `usage_records` + rate cards | Sum **estimated cost** after applying the rate-card layer (see [Cost estimation](#cost-estimation-estimated-usd-or-internal-credits)); until rate cards ship, show **raw signals** (tokens, call counts) as the primary “cost proxy.” |
| **Google API calls** | `usage_records` | Filter `job_run_id`, `provider` = `google_places` (and future Google surfaces), `usage_type` = `external_api_call`; **`metric_value`** is typically **1** per logical call; **`metric_name`** / **`metadata`** carry operation/SKU hints. |
| **Freepik API calls** | `usage_records` (**target**) | Once **`search_icons`** persists usage, filter `job_run_id`, `provider` = **`freepik`**, `usage_type` = `external_api_call`, `metric_name` = **`search_icons`**. **Not emitted today** — see [Freepik Icons API — usage attribution](#freepik-icons-api--usage-attribution-planned-not-in-runtime-yet). Use for **call volume and rate-card cost** (Freepik bills the platform, not the end user). |
| **Claude / Anthropic usage** | `usage_records` | Filter `job_run_id`, `provider` = **`anthropic`**, `usage_type` = **`llm_tokens`**; **`metadata`** holds `model`, `prompt_tokens`, `completion_tokens` where recorded. Aggregate **total tokens** and optionally **invocation count** (row count) per run. |

**Hierarchy reminder:** one **`job_runs`** row is the top-level “run” the user triggered. Under it: **`stage_runs`** → **`pipeline_run_executions`** → **`step_runs`**. Counts above are **instances executed**, not definition counts from the job YAML.

### Suggested UX flow

1. **Admin Users** (or search) → pick **user** → **Runs** tab or slide-over.
2. **Run list** (paginated, newest first): time (`created_at` / started), **status**, **trigger** / job id (from `job_runs`), optional **one-line rollup**: stage count, pipeline count, step count, **estimated cost** (or token + API call badges pre–rate-card).
3. **Run detail** for a selected `job_run_id`:
   - Summary strip: same counts + **usage breakdown** (Google calls, Freepik calls, Claude tokens/rows, other providers).
   - **Timeline or tree**: stages → pipelines → steps (reuse mental model from the pipeline editor where helpful).
   - **Step inspector**: full **`processing_log`**, I/O summaries, link to **`usage_records`** filtered by `step_run_id` when present.

### API shape (target)

* **`GET /auth/admin/users/{user_id}/runs`** — query params: `cursor` / `limit`, optional `from`, `to` (UTC). Returns run rows with **summary counts** (stages, pipelines, steps) and **usage rollups** per run. Implementation can SQL **aggregate** (`GROUP BY job_run_id`) or fetch job run ids then batch subqueries—optimize once volumes grow.

* **`GET /auth/admin/users/{user_id}/runs/{job_run_id}`** — full detail: `job_runs` row, nested stage/pipeline/step lists (or flat step list with parent ids), **`usage_records`** for that `job_run_id`.

All endpoints: **admin-only**, same authorization pattern as existing [`auth_admin`](../../../../app/routes/auth_admin.py) routes; use **Supabase service role** server-side where RLS would block cross-user reads.

### Implementation notes

* **Repository gaps:** today, `list_job_runs_by_owner` and `list_step_runs_for_job_run` exist on `PostgresRunRepository`; **listing usage by `job_run_id`**, **counting stages/pipelines per job run**, and **admin-scoped variants** (caller is admin viewing another user’s `owner_user_id`) may need new query methods or a thin **admin run service** that composes them.
* **Phase 1 `pipeline_run_events`:** the legacy queue path uses `pipeline_run_events` keyed to older **`pipeline_runs`** / platform job ids. **Datastore-backed job execution** persists operator-visible logs primarily in **`step_runs.processing_log`**. If both paths must appear in one UI, define an explicit **compat rule** (e.g. link platform job id when present); otherwise scope the explorer to **Phase 4 `job_runs` lineage** first.
* **Consistency:** “Cost” in the UI should use the same **rate-card and aggregation rules** as user-level monthly/daily summaries elsewhere in this doc, so admins and account owners do not see conflicting numbers.

---

## Admin / operator UX (target)

* **User search** → **profile strip**: last active, total runs (window), total estimated cost (window).
* **Breakdown tabs**: LLM tokens by model; external API calls by provider/operation; runs by trigger.
* **Per-user run explorer**: all runs for that user with time, structure counts, usage/cost rollups, and drill-down to step logs — see [Admin run explorer (per user)](#admin-run-explorer-per-user).
* **Drill-down**: list recent `job_runs` with links to run detail, step traces, and usage for that run.

Authentication: **admin-only** (same pattern as other `/management/*` or dedicated admin routes)—exact route shape is an implementation detail; keep **RLS** and service role rules aligned with [`global-and-per-user-resource-limits.md`](./global-and-per-user-resource-limits.md) and existing management APIs.

---

## Boundaries and coordination

* **Throughput limits** (max runs per day) consume **counts** from `job_runs` or counters; **cost monitoring** consumes **`usage_records`** and rate cards. Implementations should share **consistent definitions** of “a run” and time zones (UTC vs user-local) for product clarity.
* **Platform observability** (metrics/traces for SRE) remains in [`error-handling-observability-and-telemetry.md`](./error-handling-observability-and-telemetry.md); this doc is **product/operator analytics** on top of domain data.

---

## Phased delivery (suggested)

1. **Coverage** — Audit all step handlers and external clients; ensure every billable or capacity-relevant call produces a **`usage_record`** (or explicit non-billable flag in metadata if needed for debugging only). **Include Freepik** (`search_icons`) per [above](#freepik-icons-api--usage-attribution-planned-not-in-runtime-yet).
2. **Admin run explorer** — Admin-only **list + detail** APIs for all `job_runs` of a target user: timestamps, counts (`stage_runs`, `pipeline_run_executions`, `step_runs`), **`usage_records`** rollups (Google calls, Freepik once recorded, Claude tokens), and step-level **`processing_log`**; Admin Users UI entry point. Depends on coverage being trustworthy; can ship **raw counts/tokens** before rate cards.
3. **Rollups + API** — Nightly or incremental aggregation; minimal **admin read API** for totals by user and window (complements per-run explorer for dashboard-style summaries).
4. **Rate cards + estimated cost** — Config + calculation layer; show USD or “credits” in UI (including run list/detail).
5. **Polish** — Export, anomaly hints (spike in runs or cost), links from cost view to run detail.

---

## Open questions

* **Trigger analytics** — Is “trigger fired” strictly **run created**, or only **completed** runs? Failed runs may still incur cost—align product definition.
* **Multi-pipeline jobs** — Should “pipeline runs” be counted from `pipeline_run_executions` rather than `job_runs`?
* **Free-tier third-party APIs** — Still record **calls** even if cost is zero, so usage patterns remain visible.
* **Who can see cost** — Admin-only vs account owner self-serve (likely post-beta).

---

## Summary

The platform already persists **LLM token** and **some external API** usage via `UsageAccountingService` and `usage_records`. **Enhanced monitoring** means completing **coverage** (including **Freepik** when implemented — see [Freepik section](#freepik-icons-api--usage-attribution-planned-not-in-runtime-yet)) using a **consistent call-site usage payload** (see [Target pattern](#target-pattern-generic-usage-objects-at-api-call-sites)), supporting **non-uniform units** (e.g. per-word billing — [Generic Book Service example](#worked-example-generic-book-service-per-word-returned)), an optional **provider registry** for admin onboarding ([see above](#provider--integration-registry-admin-onboarding-target)) plus **YAML bootstrap** for shipped providers ([Bootstrapping built-in providers](#bootstrapping-built-in-providers-yaml-catalog--upsert)), defining **aggregation and rate cards**, exposing **operator-facing summaries** (including an **admin per-user run explorer**: when a run occurred, stage/pipeline/step counts, Google / **Freepik (planned)** / Claude usage, step logs), and tying **run and trigger** analytics to `job_runs`—without conflating this with **quota enforcement** (see limits doc).
