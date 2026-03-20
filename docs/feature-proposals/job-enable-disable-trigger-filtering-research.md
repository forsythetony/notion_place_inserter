# Research: Job enable/disable (active vs `disabled`) and trigger dispatch

**Intent:** Product and engineering research for letting operators **turn individual jobs on or off** while **reusing one HTTP trigger** across many jobs. When a trigger fires, the runtime should consider **only jobs that are active for execution**, not every row in the trigger–job link table.

**Primary reader:** Product + backend. Detailed schema/API work can link out to a phase doc under `docs/technical-architecture/productization-technical/` when implementation is scheduled.

**Decision:** Extend `job_definitions.status` (**Option A**) with a third lifecycle value: **`disabled`** (alongside **`active`** and **`archived`**). Trigger dispatch considers only **`active`** jobs; **`disabled`** jobs keep their trigger links but do not run from triggers.

---

## Problem

Today, a single trigger path (for example `/locations`) can be **linked to multiple job definitions** for the same owner. That is the right model when several pipelines should run on the same webhook or shortcut.

Operators also need the opposite control:

- Keep the **same trigger URL and secret** for many jobs.
- **Temporarily stop** some jobs from running when the trigger fires, **without** tearing down the trigger, **without** deleting the job graph, and ideally **without** conflating “disabled for runs” with “deleted / hidden.”

Examples:

- Seasonal or experimental job: disable until needed.
- Debug one job while others on the shared trigger keep running.
- Gradual rollout: add new linked jobs in **`disabled`** state, enable when ready.

---

## Current system behavior (as of this research)

### Job `status` field

`JobDefinition` already carries `status: str` in the domain model (`app/domain/jobs.py`). In both YAML and Postgres paths, **`archived`** is used as a **soft-delete**:

- Listings exclude archived jobs.
- `get_graph_by_id` returns `None` for archived jobs (`app/repositories/postgres_repositories.py`).
- YAML loader treats missing status as **`active`** and hides **`archived`** (`app/repositories/yaml_repositories.py`).

So **lifecycle** already has a binary: visible **`active`** vs removed-from-use **`archived`**.

### Trigger dispatch

HTTP trigger handling resolves linked job IDs via `TriggerJobLinkRepository.list_job_ids_for_trigger` (for example in `app/routes/locations.py`). That method returns **all** `job_id` values in `trigger_job_links` for the trigger and owner—**it does not join `job_definitions` or filter by job status.**

Execution then:

- **Async:** loops each `job_id`, calls `JobDefinitionService.resolve_for_run(...)`, and **skips** enqueue when resolution returns `None` (which happens for archived jobs, missing targets, etc.).
- **Sync (legacy):** uses **`job_ids[0]` only**—so ordering and archive state of the “first” linked job matter in ways that may be surprising.

**Takeaway:** Archived jobs are mostly **ineffective** on the async path because resolution fails, but **filtering is implicit and late**. There is no first-class **`disabled` but still a real definition** state, and sync behavior is fragile when the first linked job is not runnable.

---

## Goal state

1. **Explicit activation:** Each job has a clear notion of **enabled for automatic runs** (trigger-driven), distinct from **archived** (soft-delete / teardown). **`disabled`** is the “off switch” for trigger-driven execution while keeping the definition and links.
2. **Trigger processing:** When a trigger is invoked, the system should **only enqueue or execute jobs with status `active`**. Prefer **early filtering** so logs, metrics, and empty-trigger behavior are clear.
3. **Operator UX:** One place to **disable** a job **without** archiving it. In the admin **pipeline list** (one row per runnable job / pipeline definition), each row includes a compact **enabled** control—either a **checkbox** (“enabled for triggers”) or a **small toggle**—bound to `active` ↔ `disabled`. Changing it persists job `status` immediately or on save, per whatever pattern the rest of the admin uses. **`archived`** remains a separate, heavier action (not this control). Optional: muted row styling or a “Disabled” label when off.
4. **Shared trigger:** Many jobs can stay attached to one trigger; toggling **per job** controls whether that trigger affects them.

Non-goals for this research (implementation can decide later):

- Whether **manual “Run now”** from admin bypasses **`disabled`** (often **yes** for ops).
- Whether **scheduled** triggers (if added) share the same flag.

---

## Chosen approach: Option A — `status` values `active` \| `disabled` \| `archived`

| Status     | Appears in normal job lists | Trigger dispatch | Manual run (optional) |
|-----------|-----------------------------|------------------|------------------------|
| `active`  | Yes                         | Yes              | Yes                    |
| `disabled`| Yes (with state)            | **No**           | TBD (often Yes)        |
| `archived`| No / tombstone              | No               | No                     |

**Pros:** One column; migrations and YAML stay aligned; matches mental model “job status.”  
**Cons:** Validation must treat `status` as a **closed set** everywhere (API, UI, bootstrap YAML).

**Implementation sketch:**

- Postgres: constrain allowed values (check constraint or enum) when ready.
- `list_job_ids_for_trigger`: join to `job_definitions` and filter `status = 'active'` (or `NOT IN ('archived','disabled')`).
- `resolve_for_run`: optionally **reject** `disabled` / `archived` early with an explicit error reason for observability.
- Sync path: same filter as async before choosing a job to run, or deprecate single-job assumption.
- Listings: **`disabled`** jobs remain visible in admin/job lists (same as today’s intent for non-`archived` definitions); **`archived`** stays excluded from normal lists unless a special view exists.

### Alternatives considered

- **Separate boolean** (`enabled_for_trigger`): clearer separation from lifecycle but two fields to keep in sync with `archived`; rejected in favor of a single `status` enum.
- **Detach trigger links only:** no schema change, but loses intent and wiring; poor fit for shared triggers.

---

## Behavioral details to nail in an implementation spec

1. **Empty active set:** If a trigger has links but **all** linked jobs are **`disabled`** or **`archived`**, return **422** with a message distinct from “no links” (e.g. “Trigger is linked only to disabled or archived jobs”) so operators know to enable a job or fix links.
2. **Ordering:** If job order matters for sync or UX, document whether **`disabled`** jobs are omitted from ordering or appear grayed out in UI lists.
3. **Bootstrap / starter jobs:** Provisioning flows should default new jobs to **`active`** unless product wants “draft” later.
4. **Audit / observability:** Log lines such as `trigger_dispatch_skipped_job | job_id=… reason=disabled` at **dispatch** time (not only at resolve time).
5. **Management API:** PATCH job `status` or dedicated disable/enable endpoints for idempotency and clearer RBAC later.
6. **Pipeline list UI:** Implement the per-row checkbox or toggle in the pipeline list spec (or phase-5 admin doc); ensure optimistic updates or error recovery if the PATCH fails.

---

## Relationship to existing `archived`

| Concern        | `archived`              | `disabled`                          |
|----------------|-------------------------|-------------------------------------|
| Intent         | Remove from product use | Temporarily stop automatic runs     |
| Lists / editor | Hidden or tombstone     | Visible, clearly inactive           |
| Trigger        | Should not run          | Should not run                      |
| Restore        | Rare / undelete flow    | One-click re-enable (`active`)      |

**Important:** **`disabled`** jobs should **remain** in `trigger_job_links` so operators do not lose wiring when toggling.

---

## Suggested acceptance criteria (for a future implementation ticket)

- [ ] Trigger invocation (async path) **only** creates runs for jobs with status **`active`** (not **`disabled`**, not **`archived`**).
- [ ] **`disabled`** jobs remain in admin/job lists with visible state (unless product chooses to hide behind a filter).
- [ ] Archived behavior unchanged for listings and resolution.
- [ ] Clear API or admin action to **disable / enable** without deleting links; **pipeline list** shows a **checkbox or toggle per row** for this state.
- [ ] Tests covering: all linked jobs **`disabled`**, mixed **`active`** / **`disabled`**, archived linked row edge case (should not run).

---

## References in this repo

- Job domain: `app/domain/jobs.py` (`JobDefinition.status`)
- Trigger fan-out and skip logging: `app/routes/locations.py`
- Trigger–job links: `PostgresTriggerJobLinkRepository.list_job_ids_for_trigger` in `app/repositories/postgres_repositories.py`
- Archived filtering on load: `PostgresJobRepository.get_graph_by_id` in `app/repositories/postgres_repositories.py`

---

## Why this lives under `feature-proposals/`

This note is **product intent** (what operators need, scope, acceptance criteria) with enough **current-behavior context** to ground implementation. A follow-on technical spec can specify exact migrations, constraints, and route changes under `docs/technical-architecture/productization-technical/`.
