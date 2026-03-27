# Admin waitlist directory, beta waves, and invite-from-waitlist

**Status:** **Complete on 2026-03-26** · **Ready for review** — shipped per §6–§7 (v1: seeded `beta_waves`, no Waves CRUD UI).  
**Goal:** Beta user launch — operators can **see everyone on the public beta waitlist**, **search and filter** efficiently, **assign rollout waves**, and **issue invitation codes** from the same admin surface without leaving SQL or ad-hoc scripts.

**Implementation notes:**

- **Idempotent `issued_to`:** `POST .../issue-invitation` mirrors `POST /auth/invitations`: if an invite already exists for `issuedTo`, the waitlist row is **linked** to that invite when still unlinked; **409** if the row already points at a different invitation.
- **Pagination:** `GET /auth/admin/waitlist-submissions` uses cursor = base64url `{"o": offset}` and `limit` (server-backed filters + `ILIKE` search).
- **Waves:** `WAVE_1` / `WAVE_2` / `WAVE_3` seeded in migration; optional **`betaWaveId`** on invitation issue and on profiles after claim.

**Related docs:**

- [Public beta waitlist page and submission security](./public-beta-waitlist-submission-architecture.md) — public `POST /public/waitlist`, `beta_waitlist_submissions` schema, anti-abuse.
- [Admin users, invitations & cohorts UI](./admin-invitation-management-ui.md) — `/admin/users`, `POST /auth/invitations`, `user_cohorts`, cohort semantics.

---

## 1. Summary

Ship an **admin-only Waitlist tab** on the existing **`/admin/users`** page (alongside Users, Invitations, and Cohorts) that:

1. Lists all rows from `beta_waitlist_submissions` with **server-backed search and filtering** (not an unbounded client-side dump).
2. Lets admins **issue invitations** for a selected submission in context, reusing the same invitation semantics as the Invitations tab (`POST /auth/invitations`), and **links** the issued code back to the waitlist row.
3. Introduces **beta waves** — a first-class, admin-defined notion of **which rollout tranche** someone belongs to (first wave of beta, second wave, etc.), **orthogonal** to **cohorts** (audience segments for analytics).

---

## 2. Cohort vs wave (terminology)

| Concept | Purpose | Typical examples | Where it lives today |
|--------|---------|------------------|----------------------|
| **Cohort** (`user_cohorts`) | **Audience / segment** labels for analytics, reporting, and invite targeting | `STUDENT_A`, `ENGINEER_B` | `invitation_codes.cohort_id` → copied to `user_profiles.cohort_id` at claim |
| **Wave** (this doc) | **Rollout tranche** — *when* in the beta timeline someone is admitted | Wave 1 (closed alpha), Wave 2 (expanded beta), Wave 3 | New: see §5 |

**Rules of thumb:**

- A **cohort** answers “*what kind of user are they?*” (segment).
- A **wave** answers “*which admission batch / expansion step?*” (rollout order).
- The same person can be *Wave 2* and *STUDENT_A*; the dimensions are independent.

---

## 3. Why this belongs in technical architecture

This spans **admin API contracts**, **Supabase schema** (new wave dimension + waitlist linkage), **authorization** (admin-only reads of PII-heavy waitlist data), **UI patterns** (tab parity with Invitations/Users), and **operational workflow** (invite issuance tied to a waitlist row). It is not a marketing-only doc.

---

## 4. Current codebase context

### 4.1 Waitlist persistence

Table **`beta_waitlist_submissions`** (migration `20260324120000_beta_waitlist_submissions.sql`) already includes:

- Identity and form fields: `email`, `email_normalized`, `name`, `heard_about`, `work_role`, `notion_use_case`, etc.
- Workflow: `status` (default `PENDING_REVIEW`), `submission_count`, timestamps.
- Invite handoff hooks: **`invitation_code_id`**, **`invited_at`**, optional `reviewed_at`, `admin_notes`.

There is **no admin HTTP API** yet that lists or updates these rows; RLS is enabled and writes are server-side only (see public waitlist architecture doc).

### 4.2 Admin UI and invitations

- **`/admin/users`** uses a tabbed layout: Users | Invitations | Cohorts (see [admin-invitation-management-ui.md](./admin-invitation-management-ui.md)).
- **`POST /auth/invitations`** issues codes; request supports `issuedTo`, `cohortId`, `userType`, `platformIssuedOn`, etc.

### 4.3 Gap

Operators cannot yet **browse the waitlist in-product**, **filter** by status or marketing fields, **record wave assignment**, or **issue an invite** with a single workflow that **updates `invitation_code_id` / `invited_at`** on the submission.

---

## 5. Data model — beta waves

### 5.1 New table: `beta_waves`

Admin-managed catalog of rollout waves (similar in spirit to `user_cohorts`, but for **tranche**, not **segment**).

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` PK | `gen_random_uuid()` |
| `key` | `text` UNIQUE NOT NULL | Stable identifier for APIs and metrics — **UPPER_SNAKE_CASE** recommended (e.g. `WAVE_1`, `WAVE_2`) |
| `label` | `text` NOT NULL | Human label (e.g. “Wave 1 — closed alpha”) |
| `description` | `text` nullable | Optional operator notes |
| `sort_order` | `integer` NOT NULL DEFAULT 0 | Display and default ordering (lower = earlier waves) |
| `created_at`, `updated_at` | `timestamptz` | Standard |

**Constraints:** Prefer **blocking delete** (or soft-disable later) when referenced by invites, profiles, or waitlist rows — same class of problem as cohort delete semantics in the cohorts doc.

### 5.2 Foreign keys

Add nullable **`beta_wave_id uuid REFERENCES beta_waves(id) ON DELETE SET NULL`** to:

| Table | Semantics |
|-------|-----------|
| `beta_waitlist_submissions` | Planned or actual wave for this waitlist person (set before or when inviting). |
| `invitation_codes` | Wave stamped onto the code at issuance; copied to profile at claim (mirror cohort pattern). |
| `user_profiles` | Wave after the user exists (set from invitation at claim; editable in admin later if product allows). |

**Claim path:** When a profile is created or linked through a claimed invitation, if `invitation_codes.beta_wave_id` is non-null, set **`user_profiles.beta_wave_id`** from the invitation (parallel to `cohort_id`).

**Indexes:** `beta_waitlist_submissions(beta_wave_id)`, `invitation_codes(beta_wave_id)`, `user_profiles(beta_wave_id)` for admin filters and reporting.

### 5.3 Waitlist status values

Keep `status` as a **small controlled vocabulary** (exact strings enforced in app or DB check constraint). Recommended minimum set:

| Status | Meaning |
|--------|---------|
| `PENDING_REVIEW` | Default; not yet decided |
| `SHORTLISTED` | Operator interest; optional — skip if waves + notes suffice |
| `INVITED` | An invitation row is linked (`invitation_code_id` set); user may not have signed up yet |
| `DECLINED` | Explicitly not moving forward (optional) |
| `SPAM` | Classified abuse / discard (optional) |

**Transition:** Issuing an invite from the UI should set **`invitation_code_id`**, **`invited_at`**, and **`status = 'INVITED'`** (and optionally **`reviewed_at`**). Exact transitions can be tightened in implementation.

---

## 6. Admin API design

All routes require **`require_admin_managed_auth`** (same as other admin mutations). **Never** expose waitlist PII via public or non-admin authenticated routes.

### 6.1 List waitlist submissions

**`GET /auth/admin/waitlist-submissions`** (exact path can follow existing admin naming under `/auth/admin/...`)

**Query parameters (illustrative):**

| Param | Purpose |
|-------|---------|
| `q` | Search across `email`, `email_normalized`, `name`, and optionally `notion_use_case` (implementation: `ILIKE` or Postgres full-text later) |
| `status` | Filter by `status` (repeatable or comma-separated) |
| `betaWaveId` | Filter by wave |
| `heardAbout` | Filter by `heard_about` |
| `invited` | `true` / `false` — whether `invitation_code_id IS NOT NULL` |
| `sort` | e.g. `last_submitted_at_desc` (default), `created_at_asc` |
| `limit`, `cursor` | **Pagination** — avoid loading entire table into the browser |

**Response:** Page of rows with fields needed for the table and cards (ids, timestamps, status, wave summary, invite summary, truncated `notion_use_case`, etc.).

### 6.2 Patch a submission

**`PATCH /auth/admin/waitlist-submissions/{id}`**

Editable fields (v1):

- `admin_notes`
- `beta_wave_id` (nullable)
- `status` (with validation against allowed transitions)
- `reviewed_at` (optional explicit set)

**Not** editable via PATCH: raw email identity (use separate process if correction is needed); `invitation_code_id` / `invited_at` should be set via **invite issuance** flow (§6.3), not arbitrary writes, unless a dedicated “unlink mistake” admin action is added later.

### 6.3 Issue invitation from waitlist

Preferred: **one atomic server operation** so the waitlist row and invitation never drift.

**Option A — Dedicated endpoint (recommended):**

**`POST /auth/admin/waitlist-submissions/{id}/issue-invitation`**

Body: same camelCase fields as **`POST /auth/invitations`** where applicable (`userType`, `cohortId`, `platformIssuedOn`, `betaWaveId` on the invite/profile, etc.), plus optional overrides.

Server:

1. Load waitlist row; ensure not already linked to a non-revoked invite (or define idempotent rules explicitly).
2. Call existing invitation issuance service (same as `POST /auth/invitations`).
3. Update `beta_waitlist_submissions`: `invitation_code_id`, `invited_at`, `status`, optionally `beta_wave_id` from request.
4. Return the invitation payload + updated waitlist summary.

**Option B — Extend `POST /auth/invitations`** with optional `waitlistSubmissionId`:

- Simpler route surface but mixes concerns; only choose if it reduces duplication without complicating idempotency.

**Idempotency:** Align with existing **`issuedTo`** behavior: if `issuedTo` matches the waitlist email and an invite already exists, define whether the UI **surfaces the existing code** vs **errors** — document the chosen behavior in the implementation ticket.

---

## 7. Frontend architecture (`notion_pipeliner_ui`)

### 7.1 New tab: **Waitlist**

- Location: **`/admin/users`** — add **Waitlist** as a fourth tab (order suggestion: **Users | Waitlist | Invitations | Cohorts** so “people funnel” reads left-to-right, or place Waitlist adjacent to Invitations; pick one and keep router deep-links consistent).
- **Visual parity:** Reuse established admin list patterns from Invitations/Users: filter toolbar, cards/table, loading and empty states, accessible controls (see existing admin parity docs).

### 7.2 Search and filtering

- **Server-backed** list API with debounced search input and facet filters (status, wave, heard-about, invited/not).
- Do **not** rely on fetching all rows into memory except for tiny dev datasets.

### 7.3 Issue invitation UX

- Primary row action: **Issue invitation** → opens a modal **reusing** [`CreateInvitationModal`](./invitations-create-invitation-modal.md) patterns (or a thin wrapper) with:
  - **`issuedTo`** pre-filled from `email` (read-only or editable only if product allows typos),
  - optional **cohort** and **wave** selectors,
  - channel / notes as today.
- On success: show the **20-character code** with copy affordance; update row state to show **Invited** and link to invitation id/code if the UI already has a pattern for that.

### 7.4 Wave management UI

- **Minimum v1:** Wave is a **dropdown** on waitlist rows and on the issue-invite modal, populated from **`GET`** admin list of `beta_waves` (new small endpoint or bundled into existing admin bootstrap).
- **Waves admin tab (catalog CRUD):** [admin-users-waves-tab-architecture.md](./admin-users-waves-tab-architecture.md) — tab **before** Cohorts on `/admin/users/waves`; `POST/PATCH/DELETE /auth/admin/beta-waves`. Operators can also seed waves via migration SQL when needed.

---

## 8. Security and privacy

- **Admin-only:** All list/read/update/issue endpoints gated on admin role; audit in line with other admin routes.
- **PII:** Waitlist rows contain email and free text; avoid logging raw bodies at info level; respect retention policy (future work can add export/redaction — out of scope unless requested).
- **Rate limiting:** Admin APIs are authenticated; standard API rate limits apply. No change to public waitlist posting behavior.

---

## 9. Observability

- **Metrics (optional):** Count invites issued from waitlist vs ad-hoc; distribution of waves at claim time — aligns with [error-handling-observability-and-telemetry.md](./error-handling-observability-and-telemetry.md) if low-cardinality labels use `beta_waves.key`.

---

## 10. Implementation phases (suggested)

1. **Migration:** `beta_waves` + FK columns + claim-path copy for `beta_wave_id`.
2. **Backend:** Admin list (with pagination) + PATCH + issue-invitation orchestration.
3. **Frontend:** Waitlist tab + filters + issue modal integration.
4. **Polish:** Waves CRUD UI if not seeded-only; documentation and operator runbook.

---

## 11. Open decisions

- **Tab order and naming** — “Waitlist” vs “Beta waitlist” in the shell.
- **Shortlist / decline** — whether extra statuses are needed in v1 or waves + notes are enough.
- **Editing email on waitlist** — usually avoided; correction flow could be manual SQL initially.
- **Duplicate invites** — strict error vs reuse existing code when `issuedTo` matches (must match product expectation and `POST /auth/invitations` idempotency).

---

## 12. Acceptance criteria (architecture-level)

- Admins can list waitlist submissions with **search**, **filters**, and **pagination** without downloading the full table.
- Admins can **assign a wave** to a waitlist row and/or at invite time; **users** carry **`user_profiles.beta_wave_id`** after claim when the invitation carried a wave.
- Admins can **issue an invitation from a waitlist row** in one flow that **persists** `invitation_code_id` and `invited_at` on that row.
- **Cohorts** remain unchanged in meaning; **waves** are clearly separate and documented for operators.
