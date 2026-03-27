# Architecture push: First pipeline — time to value (Launch stage 1)

**Status:** **Open** — product/UX architecture; implementation partial (bootstrap APIs + Dashboard Quick Start exist; guided funnel and documentation surfacing are not done). **Review:** Ready for review (no human sign-off recorded in [`work-log.md`](../../work-log.md)).

**Launch gate:** **Launch stage 1** — with at most ten beta users, every friction point between **signup** and **first successful pipeline run** directly weakens idea validation. This doc defines the intended **minimum path**, what already exists in code, and what we should add (including an optional **step-through**).

**Audience:** Product, frontend, and backend engineers; anyone designing onboarding and bootstrap flows.

**Primary code (today):**

- Backend — `POST /management/bootstrap/create-from-template`, `POST /management/bootstrap/create-places-insertion-from-template`, `POST /management/bootstrap/reprovision-starter` in [`app/routes/management.py`](../../../../app/routes/management.py); [`PostgresBootstrapProvisioningService`](../../../../app/services/postgres_seed_service.py) (`ensure_owner_starter_definitions`, catalog seed).
- Frontend — [`DashboardPage.tsx`](../../../../../notion_pipeliner_ui/src/routes/DashboardPage.tsx) (Quick Start), [`api.ts`](../../../../../notion_pipeliner_ui/src/lib/api.ts) (`createPipelineFromTemplate`, `createPlacesInsertionPipelineFromTemplate`), Connections / OAuth routes for Notion.

---

## Executive summary

**Goal:** Minimize steps and ambiguity from **authenticated signup** to **a confirmed run** of a **template-derived** pipeline (trigger fires, worker processes, user can see success).

That requires, in combination:

1. **Template clarity** — Users know **which** template they are copying, **what** it does, and **what** must exist in Notion (e.g. template database name/shape).
2. **Notion integration** — **Connect Notion** is unavoidable; the path must be obvious before “Create from template” fails.
3. **Working bootstrap** — `create-from-template` (and any secondary template flows) **reliably** provision job, trigger, target, and links; idempotent where specified.
4. **Testable trigger** — After provisioning, the user can **invoke the trigger** (HTTP or in-app test) and **see a run** complete (Monitoring, run detail, or pipeline live test — whatever we standardize on for beta).

**Optional but high leverage:** A **linear step-through** (checklist, wizard, or progressive disclosure on Dashboard) so users are not bounced between Connections → Dashboard → Triggers without narrative.

---

## Success metrics (beta)

| Signal | Directional target |
|--------|-------------------|
| Time from first login to **first successful run** | As low as possible; measure median in Launch stage 1 |
| **Drop-off** after “Create from template” click | Reduce via pre-flight (Notion connected, template DB found) and copy |
| Support burden | Fewer “what do I do next?” threads |

---

## Intended user journey (canonical)

These steps are the **logical** order; today they are **not** all surfaced as one flow.

| Step | User outcome | Product responsibility |
|------|----------------|----------------------|
| 1 | Account exists | Signup + EULA (shipped) |
| 2 | **Notion connected** | Connections / OAuth; block or strongly steer before template provisioning |
| 3 | **Template prerequisites met** | e.g. “Oleo Places Template Database” discoverable in workspace — or document duplicate-from-Oleo template + search string |
| 4 | **Provision from template** | `POST …/bootstrap/create-from-template` succeeds (or idempotent “already exists”) |
| 5 | **Understand what was created** | Trigger URL/path, secret (once), target name — Dashboard today shows a subset |
| 6 | **Fire trigger** | User sends HTTP request or uses **live test** from UI |
| 7 | **Observe run** | Run completes; user sees result in Notion and/or in-app run history |

---

## Current implementation (grounded in repo)

### Notion OAuth

- `create-from-template` **requires** a stored Notion token; otherwise **422** with `NOTION_NOT_CONNECTED` and message to use Connections ([`management.py`](../../../../app/routes/management.py) `create_pipeline_from_template`).
- **Implication:** Any “one-click” story must **link to Connections** first or embed OAuth in the funnel.

### `POST /management/bootstrap/create-from-template`

- **Idempotent** by display name: if the template job already exists, returns `already_exists` with `/hello-world` trigger path (no new secret).
- **Flow:** OAuth → search Notion for template database by configured name → create/reuse `DataTarget` → provision trimmed pipeline + **`/hello-world`** HTTP trigger (not `/locations` — that belongs to the **starter** graph).
- **Failure modes:** **404** `TEMPLATE_DB_NOT_FOUND` with helpful lists of visible databases/pages (debuggability for support).

### Dashboard Quick Start (`notion_pipeliner_ui`)

- **Copy** explains Google Places → **Oleo Places Template Database** columns.
- **CTA:** “Create Pipeline from Template” → `createPipelineFromTemplate`.
- **Success:** Shows `trigger_path`, optional **trigger_secret** (once), `target_display_name`, links to Pipelines / Triggers.
- **Gap:** No **guided** path from zero → Notion → template DB → button; errors are generic unless we map API `code` to UI.

### Secondary template: places insertion (full job)

- **`POST /management/bootstrap/create-places-insertion-from-template`** — clones bundled `notion_place_inserter` graph with prefixed ids; separate trigger path (e.g. `/places-from-template`).
- **Dashboard:** Shown only for **allowlisted email** today — not a general beta path until product removes the gate.

### Starter job vs template pipeline

- **Starter** `job_notion_place_inserter` + **`/locations`** trigger are provisioned lazily via `ensure_owner_starter_definitions` (e.g. locations flows). See [starter job reprovision runbook](../phase-4-datastore-backed-definitions/starter-job-reprovision-runbook.md).
- **Do not conflate** starter `/locations` with Quick Start **`/hello-world`** template pipeline — different entrypoints and YAML.

### Testing a trigger

- Users need a **repeatable** recipe: copy URL + secret, `curl` or Postman, or **in-app live test** (management pipeline/trigger UIs). Exact “happy path” for beta should be **one** documented route (this doc + UX).

---

## Gaps to close (Launch stage 1)

| Theme | Gap | Proposal |
|-------|-----|------------|
| **Template documentation** | Template behavior lives in YAML/marketing; not always **in-product** next to the CTA | Short **inline** spec on Dashboard (or expandable): steps, required Notion database title, expected columns, link to deeper doc |
| **Notion connection** | User hits 422 if OAuth missing | **Pre-flight** on Dashboard: if not connected, **primary CTA** = “Connect Notion” with explanation |
| **Template DB discovery** | 404 if search misses | Surface **404** detail in UI; link to checklist: create DB from Oleo template, exact title, share to integration |
| **Create-from-template reliability** | Edge cases (schema, rate limits) | Treat failures as **product bugs** in Launch stage 1; add tests around bootstrap idempotency |
| **Test trigger + run** | User may not know how to fire `/hello-world` | After success, **step-through**: (1) copy URL (2) optional `curl` snippet (3) link to **Monitoring** or pipeline **live test** when applicable |
| **Step-through UX** | Linear journey not enforced | Optional **checklist component** or **modal wizard**: Connect → Verify template → Create → Test → Done |

---

## Proposed step-through (UX sketch)

Not a commitment to a single component — **one** of:

- **Checklist** on Dashboard with persistent completion state (`localStorage` or user profile flag).
- **Modal wizard** on first visit after signup (dismissible; re-open from Help).
- **Inline sections** that expand as prerequisites complete.

**Minimum steps in the wizard:**

1. Connect Notion (deep link to `/connections` or embedded OAuth).
2. Confirm template database exists (link to doc + “I’ve created it”).
3. Create pipeline from template (calls existing API).
4. Test trigger — show path, secret copy, **Run test** if we add a thin client to POST to the webhook or open live-test UI.

---

## Acceptance criteria (Launch stage 1)

- [ ] From a **fresh** beta account (with Notion OAuth and template DB set up), a user can follow **only in-app** navigation and copy to reach **one successful run** without asking support **for the default template path**.
- [ ] **422 / 404** from bootstrap APIs map to **actionable** UI (connect Notion, fix template DB).
- [ ] **Create from template** and **places-insertion-from-template** (if in scope for beta) are **verified** on staging: create, re-call idempotent, trigger fires.
- [ ] **Documented** “test your trigger” path (HTTP example or live test) linked from post-create success state.

---

## Related documents

- [Starter job reprovision runbook](../phase-4-datastore-backed-definitions/starter-job-reprovision-runbook.md) — `/locations` + `job_notion_place_inserter` reset; distinct from `/hello-world` template flow.
- [Data targets — source management modal](./data-targets-source-management-modal.md) — Notion data sources and refresh.
- [Beta launch readiness — hub](./README.md) — Launch stage 1 inventory.
- [Public beta waitlist](./public-beta-waitlist-submission-architecture.md) — acquisition; this doc is **in-product** time-to-value.

---

## Revision history

| Version | Date | Notes |
|---------|------|-------|
| 1 | 2026-03-26 | Initial architecture push for first-pipeline time-to-value and optional step-through. |
