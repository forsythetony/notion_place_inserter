# Architecture push: Enhanced user monitoring and cost tracking

**Status:** **Open** — implementation not started. **Review:** Ready for review (no human sign-off recorded in [`work-log.md`](../../work-log.md)).

---

## Product / architecture brief

The next and potentially most important part is **enhanced user monitoring**. When a user runs a pipeline, operators need a trustworthy picture of **activity** and **spend drivers**: how often they run work, which external capabilities each run exercises, and how much measurable usage (tokens, API calls) accumulates—eventually mapped to **estimated cost** for beta economics and capacity planning.

Concrete questions this work should answer for a given user (and optionally a time window):

* **Activity** — Active in the last week? How many **job / pipeline runs**? How many times did a given **trigger** fire (runs attributed to that trigger)?
* **LLM** — How many **tokens** were consumed via Anthropic (and later other providers), broken down by model where possible?
* **External APIs** — How many calls to **Google Places** (and field/SKU granularity later), **Notion**, **“free pick”** or other integrations?
* **Cost** — Not only raw counts: **estimated currency cost** when rate cards exist (per provider pricing model: tokens vs per-call SKUs, etc.).

Different APIs price differently: e.g. Google Places may vary by **Places API product and requested fields**; Claude-style models by **input/output tokens**. The **end state** is: pick a user → see activity, run volume, trigger attribution, token totals, per-provider call counts, and **estimated spend**—so we can reason about typical user patterns and beta burn rate.

---

## Related documents

| Topic | Doc |
|--------|-----|
| Run quotas vs usage/cost | [`global-and-per-user-resource-limits.md`](./global-and-per-user-resource-limits.md) — throughput limits (daily/monthly runs) are **enforcement**; `usage_records` here are **attribution** and cost signals. |
| Logging, metrics, tracing direction | [`error-handling-observability-and-telemetry.md`](./error-handling-observability-and-telemetry.md) — platform observability (OTEL, structured logs) complements **product** usage/cost views. |
| Historical usage design (Phase 3) | [`p3_pr08-runs-usage-observability-and-docs.md`](../phase-3-yaml-backed-product-model/p3_pr08-runs-usage-observability-and-docs.md) — introduced `UsageAccountingService` and YAML usage files. |
| Domain model | [`app/domain/runs.py`](../../../../app/domain/runs.py) — `UsageRecord`, `JobRun`, etc. |

---

## Current implementation (codebase)

### Data model: `UsageRecord`

`UsageRecord` (`app/domain/runs.py`) is the unit of persisted usage:

* `usage_type`: e.g. `llm_tokens`, `external_api_call`
* `provider`: e.g. `anthropic`, `google_places`
* `metric_name` / `metric_value`: for LLM usage, `metric_name` is `total_tokens` and `metric_value` is prompt+completion sum; for external APIs, `metric_value` is typically **1** per call (count), with `metric_name` carrying the **operation** (e.g. Places operation)
* `owner_user_id`, `job_run_id`, optional `step_run_id`
* `metadata`: e.g. for LLM: `prompt_tokens`, `completion_tokens`, `model`

Rows land in Postgres table **`usage_records`** (Phase 4 schema); persistence goes through `PostgresRunRepository.save_usage_record` (and YAML path historically in Phase 3).

### Service: `UsageAccountingService`

[`app/services/usage_accounting_service.py`](../../../../app/services/usage_accounting_service.py) exposes:

* `record_llm_tokens(...)` — persists one `UsageRecord` per invocation site; failures are logged (`usage_accounting_save_llm_tokens_failed`) and do not fail the step.
* `record_external_api_call(...)` — one row per logical external call (`metric_value=1`), with `provider`, `operation`, optional `metadata`.

`JobExecutionService` injects this as `ctx` service `usage_accounting` when a run repository is available.

### Where usage is recorded today

| Handler / area | What is recorded |
|----------------|------------------|
| `ai_prompt` | LLM tokens via `claude.get_last_usage()` → `record_llm_tokens` (`anthropic`) |
| `optimize_input` | Same pattern |
| `google_places_lookup` | `record_external_api_call` for Google Places operations (see handler for `provider` / `operation` / metadata) |

**Gaps (as of this writing):**

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
4. **Notion** — If/when metering is added, align with Notion’s billing model for the integration surface you use.

Output artifacts:

* **Estimated cost per `usage_record` row** (optional stored column populated by nightly job), or **computed only in aggregate queries**.
* **Rollups**: per user per day / per month: `sum(estimated_cost)`, `sum(tokens)`, `sum(api_calls)` by provider.

---

## Storage and aggregation

| Layer | Purpose |
|-------|--------|
| **Raw** | `usage_records` + `job_runs` (+ `step_runs` if step-level traces matter) — source of truth. |
| **Rollups** (optional but recommended for admin UI) | Periodic job or materialized view: `user_id`, `day`, `provider`, `usage_type`, `metric_key`, `sum(metric_value)`, `sum(estimated_cost)`. |
| **Rate cards** | Small config table or JSON blob with schema validation; avoid scattering magic numbers in Python. |

**Query patterns:** Admin API endpoints (future) should accept `user_id`, `from`, `to`, and return both **tables** (CSV export later) and **summary cards** (totals, top providers, top triggers by run count).

---

## Admin / operator UX (target)

* **User search** → **profile strip**: last active, total runs (window), total estimated cost (window).
* **Breakdown tabs**: LLM tokens by model; external API calls by provider/operation; runs by trigger.
* **Drill-down**: list recent `job_runs` with links to existing run detail / step traces where implemented.

Authentication: **admin-only** (same pattern as other `/management/*` or dedicated admin routes)—exact route shape is an implementation detail; keep **RLS** and service role rules aligned with [`global-and-per-user-resource-limits.md`](./global-and-per-user-resource-limits.md) and existing management APIs.

---

## Boundaries and coordination

* **Throughput limits** (max runs per day) consume **counts** from `job_runs` or counters; **cost monitoring** consumes **`usage_records`** and rate cards. Implementations should share **consistent definitions** of “a run” and time zones (UTC vs user-local) for product clarity.
* **Platform observability** (metrics/traces for SRE) remains in [`error-handling-observability-and-telemetry.md`](./error-handling-observability-and-telemetry.md); this doc is **product/operator analytics** on top of domain data.

---

## Phased delivery (suggested)

1. **Coverage** — Audit all step handlers and external clients; ensure every billable or capacity-relevant call produces a **`usage_record`** (or explicit non-billable flag in metadata if needed for debugging only).
2. **Rollups + API** — Nightly or incremental aggregation; minimal **admin read API** for totals by user and window.
3. **Rate cards + estimated cost** — Config + calculation layer; show USD or “credits” in UI.
4. **Polish** — Export, anomaly hints (spike in runs or cost), links from cost view to run detail.

---

## Open questions

* **Trigger analytics** — Is “trigger fired” strictly **run created**, or only **completed** runs? Failed runs may still incur cost—align product definition.
* **Multi-pipeline jobs** — Should “pipeline runs” be counted from `pipeline_run_executions` rather than `job_runs`?
* **Free-tier third-party APIs** — Still record **calls** even if cost is zero, so usage patterns remain visible.
* **Who can see cost** — Admin-only vs account owner self-serve (likely post-beta).

---

## Summary

The platform already persists **LLM token** and **some external API** usage via `UsageAccountingService` and `usage_records`. **Enhanced monitoring** means completing **coverage**, defining **aggregation and rate cards**, exposing **operator-facing summaries**, and tying **run and trigger** analytics to `job_runs`—without conflating this with **quota enforcement** (see limits doc).
