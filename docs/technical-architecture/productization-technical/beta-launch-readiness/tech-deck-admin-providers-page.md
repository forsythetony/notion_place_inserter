# Tech Deck: Admin Providers page (usage providers & rate cards)

**Type:** Tech Deck / delivery backlog item  
**Status:** **Not started** — spec ready for sizing and sequencing.  
**Audience:** Full-stack engineers; operators for UX review.  
**Related:** [Enhanced user monitoring and cost tracking](./enhanced-user-monitoring-and-cost-tracking.md) (Monitoring UI shipped; provider/rate data still SQL/YAML).

---

## Summary

Add an **Admin** console page (e.g. **`/admin/providers`**) where **operators** can **view**, **manage**, and **update** on the fly:

1. **`usage_provider_definitions`** — Human-facing registry: `provider_id`, display name, description, billing unit, notes (today: YAML seed + `GET /auth/admin/usage-providers`).
2. **`usage_rate_cards`** — USD hints for **`UsageCostEstimationService`**: per-provider, `usage_type` (`llm_tokens` / `external_api_call`), `rate_key` (model id, operation name, or `*`), token rates and/or `usd_per_call` (today: migrations + manual SQL).

**Goal:** Remove the need to ship migrations or run ad-hoc SQL to refresh pricing notes or rate estimates when vendors publish new list prices.

---

## Problem

- **Provider metadata** and **rate cards** are authoritative in **Postgres** but **editing** them requires **SQL**, **Supabase console**, or **new migrations**.
- **Product catalog YAML** (`product_model/catalog/usage_providers.yaml`) seeds definitions on bootstrap; drift between YAML and DB is possible if someone edits only one side.
- Operators already use **Admin → Monitoring** for run-level **estimated cost**; they cannot **adjust the inputs** (rate cards) from the same product surface.

---

## Current baseline (preserve semantics)

| Store | Role | Today’s read path |
|-------|------|-------------------|
| `usage_provider_definitions` | Labels and onboarding copy for `usage_records.provider` | `GET /auth/admin/usage-providers` |
| `usage_rate_cards` | `usd_per_million_*`, `usd_per_call`, `notes` | Loaded in admin run APIs via Supabase `select *` → `parse_rate_card_rows` |

**Estimation logic:** [`app/services/usage_cost_estimation_service.py`](../../../../app/services/usage_cost_estimation_service.py) — LLM rows match `metadata.model`; external rows match `metric_name` (operation).

**Do not break:** Hot path job execution does **not** need to read rate cards; only admin cost surfaces do. Any admin write path must stay **optional** and **validated** (bad numbers should not crash workers).

---

## Target UX (v1)

### Navigation

- **Admin** sidebar: new item **Providers** (or **Usage providers**) linking to **`/admin/providers`**.
- Order: e.g. after **Monitoring**, before or after **Theme** — follow existing `AppShell` patterns.

### Page layout (suggested)

1. **Section A — Provider definitions**  
   - Table: provider id, display name, billing unit, short description preview, updated time.  
   - Row actions: **Edit** (modal or side panel) for full fields + notes (markdown or plain text).  
   - Optional: **Add provider** (advanced — only if we validate uniqueness and alignment with runtime `usage_records.provider` strings).

2. **Section B — Rate cards**  
   - Filter chips or dropdowns: **provider**, **usage type**.  
   - Table: provider, usage type, rate key, USD fields (input/output/total token columns, per-call), effective_from, notes.  
   - Row actions: **Edit**, **Duplicate** (for a new model SKU).  
   - Inline warning when **`rate_key`** is `*` explaining fallback behavior.

3. **Help strip**  
   - Short copy: estimates are **not** billing truth; link to internal doc on SKU mapping (Google field masks, etc.).

### v2 (optional follow-ups)

- **Version history** / audit log (who changed rates, when).  
- **Import from YAML** (re-sync catalog) for disaster recovery.  
- **CSV export** of rate cards for finance.

---

## Backend / API (proposal)

All routes **`require_admin_managed_auth`**, consistent with [`app/routes/auth_admin.py`](../../../../app/routes/auth_admin.py).

| Method | Route | Purpose |
|--------|--------|---------|
| `GET` | `/auth/admin/usage-providers` | *(exists)* List provider definitions. |
| `PUT` or `PATCH` | `/auth/admin/usage-providers/{provider_id}` | Upsert or update one definition. |
| `GET` | `/auth/admin/usage-rate-cards` | List rate cards (paginate if large). |
| `PUT` or `PATCH` | `/auth/admin/usage-rate-cards/{id}` | Update one row by UUID. |
| `POST` | `/auth/admin/usage-rate-cards` | Create row (unique on provider + usage_type + rate_key). |
| `DELETE` | `/auth/admin/usage-rate-cards/{id}` | Optional; prefer soft-delete or “disable” if we need history. |

**Validation**

- **Numeric:** non-negative where applicable; allow `NULL` for unused token columns.  
- **Strings:** `provider_id` and `rate_key` length limits; no empty `provider` / `usage_type`.  
- **Concurrency:** `updated_at` or ETag optional to avoid blind overwrites.

**Caching:** If the API layer caches rate cards anywhere, invalidate on write (today rate cards are loaded per request in admin paths — confirm in code when implementing).

---

## Frontend (`notion_pipeliner_ui`)

- New route component, e.g. **`AdminProvidersPage.tsx`**, using the same admin layout and tokens as [`AdminMonitoringPage`](../../../../../notion_pipeliner_ui/src/routes/AdminMonitoringPage.tsx) / **`AppShell`**.  
- **`api.ts`:** Typed client functions for the new endpoints.  
- **Tests:** Vitest for API client + minimal route smoke (see existing admin tests).

---

## Acceptance criteria

1. Admin user can open **`/admin/providers`** and see **current** rows from **`usage_provider_definitions`** and **`usage_rate_cards`** (read parity with DB).  
2. Admin user can **edit** at least: provider **notes** / **display name**; rate card **usd_per_call**, token rates, and **notes** — persisted without a migration.  
3. Changes are visible on **next** Monitoring run detail **estimated cost** (same rate-card read path).  
4. Non-admin cannot access the page or APIs (**403**).  
5. Invalid payloads return **4xx** with clear errors; no worker crash on bad data.

---

## Risks / notes

- **YAML vs DB:** Decide whether bootstrap **overwrites** operator edits on deploy, or YAML is **dev-only** once the admin UI exists (document the rule in [`postgres_seed_service`](../../../../app/services/postgres_seed_service.py) comments).  
- **Google multi-SKU:** One `search_places` row cannot capture every field-mask combination; **notes** on the rate card row should remain the place for “verify in Cloud Billing.”

---

## Out of scope (for this Tech Deck item)

- Changing **`UsageRecord`** schema or handler instrumentation.  
- **Automatic** price ingestion from vendor APIs.  
- **Multi-currency** display (USD-only estimates today).

---

## References

- Tables: `supabase/migrations/20260322140000_usage_provider_definitions.sql`, `20260322150000_usage_rate_cards.sql` (and follow-ups).  
- Seed: `product_model/catalog/usage_providers.yaml`.  
- Admin list (read-only): `GET /auth/admin/usage-providers` in `auth_admin.py`.
