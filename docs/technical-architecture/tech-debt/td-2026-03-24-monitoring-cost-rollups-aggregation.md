# Tech Debt: Monitoring — cost rollups and aggregation

## ID

- `td-2026-03-24-monitoring-cost-rollups-aggregation`

## Status

- Open

## Related

- **Architecture (Goal 1 complete):** [Enhanced user monitoring and cost tracking](../productization-technical/beta-launch-readiness/enhanced-user-monitoring-and-cost-tracking.md) — `/admin/monitoring`, per-run `usageRollups` + `estimatedCostUsd` via `usage_rate_cards` shipped.
- **Tech Deck (open):** [Admin Providers page](../productization-technical/beta-launch-readiness/tech-deck-admin-providers-page.md) — editing rate cards without SQL (complements cost display).

## Problem / gap

The beta gate for monitoring is **met**: operators can pick a user, list runs, open run detail, and see usage rows with estimated USD. What is **not** implemented yet is **durable, scalable aggregation** of cost and usage for:

- **Large-scale or cross-user views** (e.g. dashboards over many users or long windows) without scanning raw `usage_records` repeatedly.
- **User-level summary** for a date range (totals, trend strip) **without N+1** patterns (e.g. one query per run to build a monthly total).

The architecture doc previously called out **nightly / materialized rollups** and a **user-level summary strip** as follow-ups; this ticket tracks that work explicitly.

## Direction (non-prescriptive)

- Materialized or scheduled **rollups** (by user, day/week, provider, optional cohort) stored for fast reads.
- Optional **incremental** updates vs full nightly recompute — decide under load and data volume.
- Admin UI hooks: summary row or panel on `/admin/monitoring` when product-ready (may ship after the storage/API layer).

## Exit criteria

- [ ] Documented approach (tables or views, refresh cadence, invalidation) and API shape for **aggregated** cost/usage for at least one operator workflow (e.g. user + date window totals).
- [ ] Implementation that avoids **O(runs)** per-request aggregation for common monitoring queries where rollups apply.
- [ ] [Enhanced user monitoring and cost tracking](../productization-technical/beta-launch-readiness/enhanced-user-monitoring-and-cost-tracking.md) **Remaining** section updated or superseded for rollup bullets.
