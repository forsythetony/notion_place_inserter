# Admin Users — Waves tab (`beta_waves` catalog)

**Status:** **Complete on 2026-03-26** · **Ready for review**  
**Goal:** Give operators a first-class **Waves** area on **`/admin/users`** to **create, edit, order, and (safely) retire** beta rollout waves—the same catalog that drives waitlist assignment, invitation issuance, and `user_profiles.beta_wave_id` after claim.

**Related docs:**

- [Admin waitlist directory, beta waves, and invite-from-waitlist](./admin-waitlist-waves-and-invitations-architecture.md) — data model, waitlist filters, invite flow, and **read-only** wave list in UI today (`GET /auth/admin/beta-waves` only).
- [Users & cohorts tabs — UI parity with Invitations](./admin-users-and-cohorts-ui-parity-with-invitations.md) and [Admin invitation management UI](./admin-invitation-management-ui.md) — patterns for the **Cohorts** tab and cohort CRUD to mirror for Waves.

---

## 1. Summary

Add a **Waves** tab to the admin Users shell:

1. **Placement:** Immediately **before** **Cohorts** in the tab strip (**Users → Waitlist → Invitations → Waves → Cohorts**).
2. **Purpose:** Manage rows in **`beta_waves`** (`key`, `label`, `description`, `sort_order`) without SQL or migrations for every new tranche.
3. **UX target:** **Parity with Cohorts** where it fits: list as cards (or table), copyable id/key, create modal, edit metadata, delete with clear rules when the wave is still referenced.

Deep link: **`/admin/users/waves`** (new nested route under `AdminUsersLayout`, alongside `waitlist`, `invitations`, `cohorts`).

---

## 2. Waves vs cohorts (reminder)

| Concept | Question it answers | This tab |
|--------|---------------------|----------|
| **Cohort** | *What segment is this user?* (analytics / targeting) | **Cohorts** tab — `user_cohorts` |
| **Wave** | *Which admission / rollout batch?* | **Waves** tab — `beta_waves` |

Same person can have both a cohort and a wave; dimensions stay independent. Full terminology is in the [waitlist + waves architecture](./admin-waitlist-waves-and-invitations-architecture.md) §2.

---

## 3. Current implementation vs gap

| Layer | Today | After this work |
|--------|--------|-----------------|
| **Schema** | `beta_waves` + FKs on `beta_waitlist_submissions`, `invitation_codes`, `user_profiles` (`ON DELETE SET NULL`) | Unchanged unless a follow-up migration tightens delete behavior (optional; see §6.3). |
| **Backend** | `GET /auth/admin/beta-waves` returns `{ items: [...] }` with `id`, `key`, `label`, `description`, `sortOrder`, `createdAt`, `updatedAt` | Add **POST**, **PATCH**, **DELETE** (or equivalent) for admin wave lifecycle, with validation and logging consistent with cohort admin routes. |
| **Frontend** | Waves appear only as **selectors** (waitlist, issue-invite modal) via `listAdminBetaWaves` | New **`AdminUsersWavesTab`**: full catalog management + reuse the same list API for dropdowns elsewhere. |

---

## 4. Frontend architecture (`notion_pipeliner_ui`)

### 4.1 Routing and tab order

In `main.tsx`, register **`path="waves"`** **before** **`path="cohorts"`** so route declaration order matches the intended tab order.

In `AdminUsersLayout` (`AdminUsersPage.tsx`):

- Insert **NavLink** **Waves** with `to="/admin/users/waves"` **immediately before** the Cohorts link.
- Update page title / intro copy if it still implies only “cohorts” for catalog management (optional polish).

### 4.2 UI patterns

Mirror **Cohorts** tab patterns already in the codebase:

- **List:** Sorted by **`sortOrder`** then **`key`** (match `SupabaseAuthRepository.list_beta_waves` ordering).
- **Card content:** stable **`key`** (badge), **`label`**, **`description`**, **`sortOrder`**, ids, timestamps, **copy key** affordance.
- **Create:** modal — **`key`** (UPPER_SNAKE_CASE convention, validated server-side), **`label`**, optional **`description`**, optional **`sortOrder`** (default sensible, e.g. append after last).
- **Edit:** modal or inline — at minimum **`label`**, **`description`**, **`sort_order`**; **`key`** usually **immutable** after create (if renamed, treat as new wave + migration of references — out of scope unless explicitly required).
- **Empty / loading / errors:** same admin section classes as Cohorts (`admin-users-section`, toolbars, muted text).

### 4.3 API client

Extend `api.ts` with **`createAdminBetaWave`**, **`patchAdminBetaWave`**, **`deleteAdminBetaWave`** (names aligned with existing `listAdminBetaWaves`) and types mirroring JSON shapes from the backend.

### 4.4 Tests

- **Router:** `router.test.tsx` — visiting `/admin/users/waves` renders Waves tab for admin.
- **API:** `api.test.ts` — request paths and methods for new endpoints.

---

## 5. Backend architecture (`app/`)

All routes stay under the existing **admin auth** router prefix (same **`require_admin_managed_auth`** as `GET /auth/admin/beta-waves` and cohort routes).

### 5.1 List (existing)

**`GET /auth/admin/beta-waves`** — keep; ensure sort order remains **(`sort_order`, `key`)** for stable UI.

### 5.2 Create

**`POST /auth/admin/beta-waves`** — `201`

Body (camelCase in API, consistent with cohort create):

| Field | Required | Notes |
|--------|----------|-------|
| `key` | yes | Unique; normalize / validate (e.g. trim, recommend `WAVE_N` style). |
| `label` | yes | Display name. |
| `description` | no | Operator notes. |
| `sortOrder` | no | Integer; default e.g. `max(sort_order)+10` or next step in implementation. |

**409** if `key` already exists.

### 5.3 Patch

**`PATCH /auth/admin/beta-waves/{wave_id}`**

| Field | Notes |
|--------|--------|
| `label`, `description` | Optional strings. |
| `sortOrder` | Optional integer — **reordering** waves. |

**`key`** — omit from v1 PATCH or explicitly forbid changes (prefer immutability).

### 5.4 Delete

**`DELETE /auth/admin/beta-waves/{wave_id}`** — `204`

**Semantics:** Prefer **cohort-like safety**:

- **204** if deleted successfully.
- **404** if unknown id.
- **409** if still **referenced** by any of `beta_waitlist_submissions`, `invitation_codes`, or `user_profiles` — operators must reassign or clear those rows first.

Implement via **pre-delete counts** in `SupabaseAuthRepository` (or dedicated helper), **not** relying on operators to remember that DB FKs currently **`ON DELETE SET NULL`** (silent data change is worse than a clear **409** for admin UX).

Optional later migration: change FKs to **`ON DELETE RESTRICT`** so the database enforces the same rule as the app.

### 5.5 Repository

Add **`create_beta_wave`**, **`update_beta_wave`**, **`delete_beta_wave_if_unused`** (or named analogously to cohort helpers) in **`SupabaseAuthRepository`**, reusing the configured **`table_beta_waves`**.

### 5.6 Logging and errors

- Structured logs for create/patch/delete with `admin_user_id`, `wave_id`, `wave_key`.
- **400** for validation failures; **409** for conflicts (duplicate key, delete in use).

### 5.7 Tests

- **`tests/test_admin_waitlist_routes.py`** (or a focused `test_admin_beta_waves_routes.py`): happy paths + 404/409/duplicate key.

---

## 6. Operator workflow

1. **Define waves** — e.g. “Wave 4 — design partners” with `sortOrder` after existing seeds.
2. **Assign on waitlist** — PATCH submission `betaWaveId` (already supported).
3. **Issue invites** — `betaWaveId` on invitation (already supported).
4. **Retire a wave** — only after no rows reference it, or after bulk reassignment (future bulk tools out of scope unless requested).

---

## 7. Security and privacy

- **Admin-only** — same gate as other `/auth/admin/*` directory routes.
- **No PII** on `beta_waves` rows; low sensitivity, still audit mutations.

---

## 8. Acceptance criteria (architecture-level)

- **Tab** **Waves** appears **before** **Cohorts** on **`/admin/users`**, with route **`/admin/users/waves`**.
- Admins can **list**, **create**, **update** (label, description, sort order), and **delete** waves subject to **not-in-use** delete rules.
- **Waitlist** and **Create invitation** wave dropdowns continue to use the **same** list endpoint (refreshed after mutations).
- Behavior is **documented** for operators: waves are **rollout batches**, not cohorts.

---

## 9. Implementation phases (suggested)

1. **Backend:** POST / PATCH / DELETE + repository methods + tests.
2. **Frontend:** route, tab, modals/cards, `api.ts`, styles reuse from Cohorts.
3. **Polish:** page title copy, optional “references” hint on delete error (counts per table).

---

## 10. Open decisions

- **`key` mutability** — default **immutable** after create; if product needs rename, add a dedicated “duplicate wave + migrate” flow later.
- **`sortOrder` UX** — numeric field vs drag-and-drop reorder (numeric is enough for v1).
- **Bulk assign wave** on waitlist — separate ticket if operators need multi-select PATCH.
