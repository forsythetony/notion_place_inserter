# Admin users, invitations & cohorts UI

**Status:** Complete (2026-03-22) — spec delivered and shipped; see `work-log.md` Log (e.g. `admin-invitation-management-ui`, `admin-user-email-display-search`).  
**Goal:** Beta user launch — operators can issue, inspect, and revoke invitation codes from the product UI without relying on CSV/CLI alone, on a **single admin page** that also exposes a **bare-bones read-only** user list and **cohort** management. **Cohorts** segment beta participants (e.g. students vs engineers vs sales) for **analytics and metrics**; each invite can pin a user to a cohort at sign-up.

---

## 1. Summary

Deliver an **admin-only** surface in `notion_pipeliner_ui` using a **tabbed layout**:

| Tab | Priority | Purpose |
|-----|----------|---------|
| **Invitations** | **Primary** | Full workflow: create (incl. optional **cohort**), list/filter, revoke (see below). |
| **Users** | **Secondary (v1)** | Minimal read-only visibility into who has a profile — not full user administration. Includes **cohort** column when set. |
| **Cohorts** | **Secondary (v1)** | Define and describe cohorts (e.g. `STUDENT_A`); used when issuing invites and stamped onto profiles at claim. |

**Invitations tab** — an administrator can:

1. **Create** an invitation: choose target user label (`issuedTo`), optional **channel** (`platformIssuedOn`), `userType`, and optional **cohort** (select from existing `user_cohorts` rows — see §3.4); the backend returns a **20-character** invite code (no requirement to send email from the app).
2. **List** existing invitation codes with enough metadata to see whether each is **claimed**, **still claimable**, who it was issued for, **which cohort** (if any) applies, and when it was issued/claimed. In v1 the admin **GET** returns **every** row; **search and filters** (channel, issued-to text, etc.) run **only in the browser** on that payload.
3. **Delete** (revoke) an **unclaimed** code so it can no longer be used.

**Users tab** — read-only list of `user_profiles` (see §5.5), including **`cohortId` / cohort label** when present, plus **email** resolved from Supabase Auth (`GET /auth/admin/user-profiles` enriches rows via `auth.admin.list_users`). No editing, no role changes, no deletes in v1.

**Cohorts tab** — administrators **create**, **list**, and **edit descriptions** for cohort records (see §5.6, §7.5). Cohort **keys** are stable identifiers (e.g. `STUDENT_A`, `ENGINEER_B`) suitable for metrics labels; descriptions are human-readable (e.g. “University pilot — cohort A”). v1 avoids deleting cohorts that are referenced by invites or profiles (see §5.6).

**Sign-up / claim path** — When a user completes sign-up using an invitation code, the **`cohort_id` on that invitation row** (if non-null) is **copied to `user_profiles.cohort_id`**. Unclaimed codes with no cohort still produce users with no cohort.

**Routing:** one route **`/admin/users`** (name reflects “people in the system”; **Users** tab is the default child route). Register next to the existing admin Theme page. **Nav:** a single admin item (**“Users”** in the shell) pointing at `/admin/users`. Deep links cover **three** tabs: **users**, invitations, cohorts (left-to-right: Users | Invitations | Cohorts).

---

## 2. Product goals and non-goals

### Goals

- Replace ad-hoc CLI/CSV flows for day-to-day beta invites with a first-class UI path.
- Single source of truth for “what codes exist and their state” visible to admins inside the app.
- Same authorization model as other admin mutations: **only `user_type === ADMIN`** via managed Supabase auth.

### Non-goals (this iteration)

- **Renaming** a cohort **`key`** from the admin UI (would break metric continuity); v1 allows **description** edits only via **PATCH** (§5.6). A dedicated rename/migration flow is a later story if needed.
- **Outbound email** or Slack delivery of codes (manual copy/paste remains OK).
- **Batch import** in the browser (the existing [`helper_scripts/invitation_csv_issuer`](../../../../helper_scripts/invitation_csv_issuer/README.md) remains the bulk path).
- **Editing** a row after creation (issue is idempotent by `issuedTo` only for duplicate detection; changing metadata is out of scope unless we add explicit PATCH later).
- **End-user** listing of codes (never exposed outside admin).
- **Full user administration** on the **Users** tab: no suspend/delete, no role changes — v1 is **read-only profile rows** plus **email display** from Auth (§5.5, §7.3).

---

## 3. Current backend and data model (as implemented)

### 3.1 Persistence

`invitation_codes` is defined in migration [`20260313130000_phase2_pr01_auth_schema_user_profile_invite_codes.sql`](../../../../supabase/migrations/20260313130000_phase2_pr01_auth_schema_user_profile_invite_codes.sql):

| Column | Purpose |
|--------|---------|
| `id` | UUID primary key |
| `code` | Unique, exactly **20** characters |
| `user_type` | `ADMIN` \| `STANDARD` \| `BETA_TESTER` |
| `issued_to` | Free-text label (e.g. email) for ops; used for **idempotent re-issue** |
| `platform_issued_on` | Free-text **channel** / source (e.g. `beta-email`, `linkedin`) |
| `claimed`, `date_claimed`, `claimed_at`, `claimed_by_user_id` | Claim lifecycle |
| `date_issued`, `created_at` | Issuance timestamps |

**Cohort columns** (`cohort_id` on `invitation_codes` and `user_profiles`, plus table `user_cohorts`) are specified in **§3.4** — not present until that migration lands.

`user_profiles.invitation_code_id` references `invitation_codes(id)` **ON DELETE SET NULL** — deleting an invite row clears the FK on the profile but does not delete the user.

### 3.2 Implemented HTTP API

Router: [`app/routes/invitations.py`](../../../../app/routes/invitations.py), mounted at `/auth/invitations`.

| Method | Path | Auth | Role |
|--------|------|------|------|
| `POST` | `/auth/invitations` | Bearer | **`require_admin_managed_auth`** — issue code |
| `POST` | `/auth/invitations/validate` | Bearer | Any authenticated user with profile |
| `POST` | `/auth/invitations/claim` | Bearer | Post-signup claim |
| `POST` | `/auth/invitations/claim-for-signup` | Bearer | Signup orchestration |

**Issue request body (camelCase in JSON):** `userType`, optional `issuedTo`, optional `platformIssuedOn`, optional **`cohortId`** (UUID of a `user_cohorts` row — see §3.4, §5.6).

**Issue behavior:** If `issuedTo` is non-empty and an invitation already exists for that exact string, the API returns the **existing** row (idempotent) — see [`tests/test_invitation_routes.py`](../../../../tests/test_invitation_routes.py). Idempotent re-issue behavior should **not** silently change `cohort_id` on an existing row unless product explicitly defines a PATCH; v1 can **reuse the existing invitation unchanged** (including cohort).

**Gap for this feature:** There is **no** admin `GET` (list) or `DELETE` (revoke) endpoint yet. Repository [`SupabaseAuthRepository`](../../../../app/services/supabase_auth_repository.py) supports create, read-by-code, read-by-issued-to, validate, and claim — **not** list-all or delete-by-id.

### 3.3 Operational path today

- [`helper_scripts/invitation_csv_issuer`](../../../../helper_scripts/invitation_csv_issuer/README.md) calls `POST /auth/invitations` with admin credentials.

### 3.4 `user_cohorts` and cohort assignment (new migration)

**Purpose:** Segment beta testers for **metrics and reporting** (e.g. students vs engineers vs sales) without overloading `user_type`. Cohort is **optional** on both invitations and profiles.

**New table: `user_cohorts`**

| Column | Purpose |
|--------|---------|
| `id` | UUID primary key |
| `key` | **Unique.** Stable identifier for APIs and metrics — **UPPER_SNAKE_CASE** recommended (e.g. `STUDENT_A`, `ENGINEER_COHORT`). Not renamed after use in production if avoidable. |
| `description` | Optional human-readable text (audience, pilot wave, notes). |
| `created_at`, `updated_at` | Timestamps |

**Alter existing tables (FK to `user_cohorts(id)`):**

| Table | Column | Semantics |
|-------|--------|-----------|
| `invitation_codes` | `cohort_id` | Nullable. If set, a successful **claim** copies this value to the new or updated profile. `ON DELETE SET NULL` if a cohort row is removed (prefer blocking delete while referenced — see §5.6). |
| `user_profiles` | `cohort_id` | Nullable. Set at **sign-up / claim** from the invitation’s `cohort_id`; thereafter read-only in v1 admin UI (display only on **Users** tab). |

**Sign-up / claim behavior:** Extend the existing invitation **claim** and **claim-for-signup** paths (Phase 2 — [p2_pr03](../phase-2-authentication-segmentation/p2_pr03-invitation-code-issuance-and-claim-service.md)) so that when a profile is created or linked to a claimed code, **`user_profiles.cohort_id`** is set from **`invitation_codes.cohort_id`** for that code. Codes with `cohort_id IS NULL` yield users with no cohort.

**CSV / CLI issuer:** [`helper_scripts/invitation_csv_issuer`](../../../../helper_scripts/invitation_csv_issuer/README.md) can be extended later to pass `cohort_id` or `cohort_key`; v1 product focus is the admin UI.

**Downstream metrics:** Cohort **`key`** is the preferred **low-cardinality** label for dashboards and telemetry (aligned with [error-handling-observability-and-telemetry.md](./error-handling-observability-and-telemetry.md) and [enhanced-user-monitoring-and-cost-tracking.md](./enhanced-user-monitoring-and-cost-tracking.md)).

---

## 4. Authorization model — admin-only UI and API

**Principle:** The **user management page** (`/admin/users` and its tabs) and **every** backend route it uses are **restricted to `user_type === ADMIN`**. Authorization is **always enforced on the API** (`403` for authenticated non-admins, `401` when unauthenticated per existing auth). The **frontend** guard (nav visibility + route protection) is **defense in depth** — not a substitute for server checks.

### 4.1 UI (`notion_pipeliner_ui`)

- **Nav:** Render the **Users** / **Users & invites** (or equivalent) admin nav item **only** when `user_type === "ADMIN"` — same pattern as the Theme admin link — see [`AppShell.tsx`](../../../../../notion_pipeliner_ui/src/layouts/AppShell.tsx) and `GET /management/account` (`getManagementAccount`).
- **Route guard:** The **`/admin/users`** route (including deep-linked tab paths) must **not** expose the management UI to non-admins: **redirect** (e.g. home or dashboard) or a clear **access denied** state **before** rendering lists or calling admin APIs. Avoid **flashing** sensitive chrome while account role is loading.
- **Direct URL:** A signed-in **non-admin** who opens `/admin/users` manually must still see **no** invitation or directory data; any API calls from the page must receive **403** and the UI should handle that without leaking content.

### 4.2 API (FastAPI)

Use **`require_admin_managed_auth`** on **all** routes for this feature — the same dependency as issuance (`POST /auth/invitations`). It validates the Supabase Bearer JWT, loads `user_profiles`, and requires `user_type == "ADMIN"`; otherwise **403** `Admin access required`. Reference: [`app/dependencies.py`](../../../../app/dependencies.py).

**Reads are not public:** Admin **GET** endpoints (invitation lists, user profiles, cohort lists) return **sensitive operational data** (invite codes, user ids). They use the **same** admin dependency as **POST / PATCH / DELETE** — not `require_managed_auth` alone.

| Endpoint | Methods | Admin only |
|----------|---------|------------|
| `/auth/invitations` | `POST` (issue, existing) | Yes |
| `/auth/invitations` | `GET` (list, §5.1) | Yes |
| `/auth/invitations/{invitation_id}` | `DELETE` (§5.2) | Yes |
| `/auth/admin/user-profiles` | `GET` (§5.5) | Yes |
| `/auth/admin/cohorts` | `GET`, `POST` (§5.6) | Yes |
| `/auth/admin/cohorts/{cohort_id}` | `PATCH`, `DELETE` (§5.6) | Yes |

**Out of scope for this table:** `validate`, `claim`, and `claim-for-signup` remain **non-admin** invitation flows for end users (§3.2).

---

## 5. Proposed API additions

Implement invitation **list/delete** in the same router (`/auth/invitations`) for consistency and OpenAPI grouping. The **user profile list** (§5.5) uses a separate **`/auth/admin/...` prefix** so admin-only “directory” reads stay distinct from invitation code CRUD; mount it alongside the existing auth routes (same dependency: `require_admin_managed_auth` — see §4.2).

### 5.1 `GET /auth/invitations`

- **Auth:** `require_admin_managed_auth`
- **Purpose:** Return **every** invitation row for the admin UI to render and filter **entirely on the client** in v1.

**No query parameters in v1.** There is **no** server-side filtering: no `q`, `claimed`, `user_type`, `platformIssuedOn`, `limit`, or `cursor`. The handler loads **all** invitation codes the admin is allowed to see (single `select` ordered by `created_at` descending for a sensible default table order).

**Rationale:** Beta volume is expected to stay small; keeping the API dumb avoids query-string complexity. **Later** (when row counts or performance demand it), add optional filters and/or pagination on the server — out of scope for v1.

**All filtering is frontend-only (v1, decided):** Search / “username” (issued-to) text box, **channel** dropdown, **claimed** / **user_type** toggles if present — every control operates on **in-memory copies** of `items` returned by this GET. Channel options come from **distinct non-empty `platformIssuedOn`** values in that payload. There is **no** fixed channel schema; `platform_issued_on` remains free text in the DB. **No** dedicated `GET …/channels` endpoint.

**Response shape (illustrative):**

```json
{
  "items": [
    {
      "id": "uuid",
      "code": "…20 chars…",
      "userType": "BETA_TESTER",
      "cohortId": "uuid-or-null",
      "cohortKey": "STUDENT_A-or-null",
      "issuedTo": "user@example.com",
      "platformIssuedOn": "beta-waitlist",
      "claimed": false,
      "dateIssued": "2026-03-21T12:00:00Z",
      "dateClaimed": null,
      "claimedAt": null,
      "claimedByUserId": null,
      "createdAt": "2026-03-21T12:00:00Z"
    }
  ]
}
```

Use **camelCase** aliases in Pydantic models to match existing invite routes and the frontend.

**Ordering (API response):** `created_at` descending (newest first); the UI may re-sort client-side if needed.

**UI copy:** Show how many invitations were loaded (e.g. **“N invitations”** or **“Loaded N invitation(s)”**). No “200 cap” messaging — v1 loads the **full** set. If the product later caps or paginates, update this copy accordingly.

### 5.2 `DELETE /auth/invitations/{invitation_id}`

- **Auth:** `require_admin_managed_auth`
- **Purpose:** Revoke an **unclaimed** code (delete row).

**HTTP semantics (v1, decided):**

| Situation | Status | Body |
|-----------|--------|------|
| Row not found | **404** | `{"detail": "…"}` (deterministic message) |
| Row exists but **`claimed == true`** | **409 Conflict** | `{"detail": "…"}` — cannot delete claimed invitations (audit / `user_profiles.invitation_code_id`) |
| Row exists, **unclaimed**, delete succeeds | **204 No Content** | Empty body |

**Repository (v1):** Load row by `id` → branch **404** / **409** → else **delete** by `id` (or a single conditional delete that returns affected count, then map 404/409 from prior fetch). **No RPC** in v1; a plain filtered delete on `id` + `claimed = false` is enough if the route first resolves existence/claimed state.

### 5.3 `GET /auth/invitations/{invitation_id}`

**Out of scope for v1.** The list endpoint (§5.1) is sufficient. Add a detail endpoint only if the UI needs lazy-loaded rows later.

### 5.4 Existing `POST /auth/invitations`

**Extend** the create contract with optional **`cohortId`** (UUID of a `user_cohorts` row). If omitted, `invitation_codes.cohort_id` is null. **Validate** that `cohortId` references an existing row when present (**400** if invalid). The create form and CSV issuer (when updated) share this shape.

### 5.5 `GET /auth/admin/user-profiles` (Users tab — bare bones)

- **Auth:** `require_admin_managed_auth`
- **Purpose:** Return **every** `user_profiles` row for the **Users** tab read-only table. Same “small beta volume, load all, filter on client if we add it later” rationale as §5.1.

**No query parameters in v1.** Order by `created_at` descending (newest first).

**Response shape (illustrative, camelCase):**

```json
{
  "items": [
    {
      "userId": "uuid",
      "userType": "BETA_TESTER",
      "invitationCodeId": "uuid-or-null",
      "cohortId": "uuid-or-null",
      "cohortKey": "STUDENT_A-or-null",
      "createdAt": "2026-03-21T12:00:00Z",
      "updatedAt": "2026-03-21T12:00:00Z"
    }
  ]
}
```

**Join:** `cohortKey` (and optionally a short `cohortDescription` snippet) comes from a **left join** to `user_cohorts` on `user_profiles.cohort_id` so the **Users** tab is readable without N+1 lookups.

**Non-goals for this endpoint (v1):** No email or `auth.users` fields (those require Supabase Auth admin or a secure join strategy — defer unless product demands it for beta). No pagination until row counts force it.

**Repository:** Add `list_user_profiles_for_admin(...)` on [`SupabaseAuthRepository`](../../../../app/services/supabase_auth_repository.py) — `select` from `user_profiles` with optional join to `user_cohorts`, order `created_at` desc, no limit.

### 5.6 Cohort admin API (`/auth/admin/cohorts`)

- **Auth:** `require_admin_managed_auth` for all routes below.

**`GET /auth/admin/cohorts`**

- Return **all** `user_cohorts` rows for the admin UI (small beta volume — **no** pagination in v1).
- **Response:** `{ "items": [ { "id", "key", "description", "createdAt", "updatedAt" } ] }` (camelCase).

**`POST /auth/admin/cohorts`**

- **Body:** `{ "key": "STUDENT_A", "description": "optional" }` — validate `key` format (non-empty, unique, recommend UPPER_SNAKE_CASE in app).
- **201** with created row; **409** if `key` duplicates.

**`PATCH /auth/admin/cohorts/{cohort_id}`**

- **Body:** `{ "description": "…" }` only in v1 — **do not** rename `key` via PATCH (avoids breaking metrics continuity); add a separate “rename key” story later if needed.

**`DELETE /auth/admin/cohorts/{cohort_id}`**

- **409 Conflict** if any `invitation_codes` or `user_profiles` row references this cohort (prefer **block** over cascade for audit clarity).
- **204** if no references and delete succeeds; **404** if missing.

---

## 6. Repository and performance notes

Add to [`SupabaseAuthRepository`](../../../../app/services/supabase_auth_repository.py):

- `list_invitation_codes(...)` — `select *` on `invitation_codes` (include `cohort_id`; optional join to `user_cohorts` for `cohortKey` in list), **`.order("created_at", desc=True)`**, **no** `limit` / **no** `where` filters in v1 (return full table for admin).
- `list_user_profiles_for_admin(...)` — `select` on `user_profiles` **left join** `user_cohorts`, **`.order("created_at", desc=True)`**, **no** `limit` in v1 (§5.5).
- `delete_unclaimed_invitation_by_id(id)` — delete where `id` matches and `claimed` is false, or helpers: `get_invitation_by_id`, `delete_invitation_row(id)` used from the route after 404/409 checks.
- Cohort helpers: `list_cohorts`, `create_cohort`, `update_cohort_description`, `delete_cohort_if_unused` (or equivalent) backing §5.6.

**List volume:** v1 assumes a **modest row count**. If the table grows large, add **pagination + server-side filters** (see §5.1 “Later”) before the UI becomes unusable.

**Secrets:** Full codes are shown **only** to admins over HTTPS; avoid logging full codes in application logs (existing code already truncates in some log lines).

---

## 7. Frontend architecture (`notion_pipeliner_ui`)

### 7.1 Routing and navigation

- Add route **`/admin/users`** (**signed-in + `user_type === ADMIN` only** — see §4.1). **Default tab:** **Users** (nested index redirects to `/admin/users/users`); **Invitations** remains the primary *workflow* for issuing codes via deep link `/admin/users/invitations`.
- **Deep-linking (recommended):** support **`/admin/users/invitations`**, **`/admin/users/users`**, and **`/admin/users/cohorts`** as child paths **or** `?tab=…` for each so every tab is bookmarkable without fragile client-only state. Pick one pattern and use it consistently in `navItems` and internal links.
- Register in [`main.tsx`](../../../../../notion_pipeliner_ui/src/main.tsx) / router alongside [`AdminThemePage`](../../../../../notion_pipeliner_ui/src/routes/AdminThemePage.tsx). Implementation can be one parent route component with nested routes or a single page with tab state driven by the URL.
- Extend [`AppShell`](../../../../../notion_pipeliner_ui/src/layouts/AppShell.tsx) **admin** `navItems` with **one** entry, e.g. `{ to: "/admin/users", label: "Users" }` or `{ to: "/admin/users/invitations", label: "Users & invites" }`, adjacent to Theme — avoid separate nav rows for Invitations vs Users vs Cohorts; the **tabs** replace that split.

### 7.2 Tab: Invitations (primary)

This tab carries the bulk of UX polish and testing effort.

1. **Issue form:** fields for `issuedTo` (text), `platformIssuedOn` (free text for channel label on create — optional), `userType` (select), **cohort** (select — options from `GET /auth/admin/cohorts`; include **“None”** / null). Submit → `POST /auth/invitations` with optional `cohortId` → show returned **code** with **copy** button; surface idempotent return (same code if `issuedTo` duplicate). After a successful issue, **refetch** `GET /auth/invitations` (or append locally) so the table stays in sync. **Prefetch cohorts** when the Invitations tab mounts (or lazy-load on cohort dropdown focus) so the form is usable without visiting the Cohorts tab first.
2. **Initial load (when tab is active or on mount):** `GET /auth/invitations` once; store `items` in component state (or React Query).
3. **List toolbar (all client-side):** **Search** — text input filters rows in memory (e.g. match substring on `issuedTo`, case-insensitive). **Channel** — dropdown: **“All”** plus distinct `platformIssuedOn` from current `items`. **Claimed** / **user type** — optional dropdowns or toggles that filter the same in-memory list. Optional **cohort** filter (all / specific `cohortKey`). **No refetch** when filters change — only when the list data must be refreshed (after issue, after delete, manual refresh if offered).
4. **Table:** columns — code (monospace), user type, **cohort** (key or “—”), issued to, channel, claimed badge, issued date, claimed date, claimed-by user id (truncated), actions (delete for unclaimed only). Show **count** of loaded invitations (§5.1).
5. **Errors:** Map 401/403/400/409 to inline alerts; reuse patterns from `AdminThemePage` / `fetchWithBearer` in [`api.ts`](../../../../../notion_pipeliner_ui/src/lib/api.ts).

### 7.3 Tab: Users (bare bones)

Read-only **supporting** surface — enough to correlate invites with accounts without building a full admin CRM.

1. **Load:** `GET /auth/admin/user-profiles` when the Users tab is first shown (or prefetch on page mount — either is fine; avoid duplicate fetches on tab churn if using React Query `staleTime`).
2. **Presentation:** Card layout (see styleguide) with **email** (from Auth) and **user type** in the header; body includes **User ID**, **Invitation code ID**, **Cohort**, **Created**, **Updated**. Show row count (e.g. **“Showing N of M”**).
3. **Copy:** No create/edit/delete buttons in v1.
4. **Empty / error:** Same alert patterns as Invitations; empty list is valid.

### 7.4 Tab: Cohorts (management)

1. **Load:** `GET /auth/admin/cohorts` when the Cohorts tab is first shown (or prefetch on admin page mount).
2. **Create:** form with **Key** (e.g. `STUDENT_A`) and optional **Description** → `POST /auth/admin/cohorts`. Surface **409** if key duplicates.
3. **List/table:** columns — **Key**, **Description** (truncate with tooltip if long), **Created**, **Updated**. Row actions: **Edit description** (inline modal or small form → `PATCH`). **Delete** only when API returns success (no references); otherwise show **409** message (explain that cohort is in use).
4. **Empty / error:** Same alert patterns as other tabs.

### 7.5 Shared page chrome

- **Page title** can read **“Users, invitations & cohorts”** or **“Admin — users”** with subhead clarifying tabs.
- **Tab control:** **Users | Invitations | Cohorts** (left to right); **Users** is the default landing tab for `/admin/users`.

---

## 8. Audit and observability

- **Structured logs** (loguru): on issue (already partially present), add **list invitations**, **list user profiles**, **delete invitation**, **cohort CRUD** with `admin_user_id`, `invitation_id` (for delete), `cohort_id` / `cohort_key` where relevant, and **never** log full invite code (optional: last 4 chars).
- **Metrics** (if/when metrics exist): `admin_invitations_issued_total`, `admin_invitations_revoked_total` — optional for beta. **Product / beta analytics** should prefer **`cohort_key`** (or `cohort_id` mapped in the warehouse) as a **low-cardinality** dimension on usage and cost events once profiles carry cohort (§3.4).

No separate audit table is required for MVP if DB rows remain the source of truth and deletes are restricted to unclaimed rows.

---

## 9. Testing plan

| Layer | What to add |
|-------|-------------|
| **Backend** | Extend [`tests/test_invitation_routes.py`](../../../../tests/test_invitation_routes.py): `GET /auth/invitations` **200 OK** for admin with full `items` (no query params); non-admin **403**; delete unclaimed **204**; delete claimed **409**; list ordered newest-first. Add coverage for **`GET /auth/admin/user-profiles`** (with cohort join fields) and **`/auth/admin/cohorts`** CRUD: admin **200**/expected status codes; non-admin **403**. **`POST /auth/invitations`** with `cohortId` persists `cohort_id`. **Claim / claim-for-signup:** integration or unit tests that **`user_profiles.cohort_id`** matches the invitation when the code carries a cohort. |
| **Repository** | Unit tests with mocked Supabase client: invitation list returns all rows (no server filters); user profile list with cohort join; delete conditional; cohort create/update/delete guarded. |
| **Frontend** | Component/route tests: non-admin cannot see nav or gets redirect; happy path mocked API for **all three** tabs; Invitations: search/channel/claimed/cohort filters operate on in-memory `items` where applicable (§5.1); Users: table renders cohort column; Cohorts: create + edit description; tab URL or query preserves selection if implemented (§7.1). |

---

## 10. Acceptance criteria

1. Admin can **create** an invitation from the **Invitations** tab and see the **generated code** with copy affordance.
2. Admin can **see a list** of **all** loaded invitations with **claimed vs unclaimed** clearly indicated and key metadata (`issuedTo`, `platformIssuedOn`, dates, `userType`, **cohort**), and the UI shows **how many** were loaded (§5.1).
3. Admin can **delete** an **unclaimed** invitation; **cannot** delete a claimed one (clear error).
4. Non-admin users **cannot** call **any** admin management API — **including all GET list endpoints** (invitations, user profiles, cohorts) and **POST / PATCH / DELETE** (§4.2) — **403**; they **cannot** use the **`/admin/users`** UI (nav hidden, route guard + no data flash).
5. Idempotent **issue** behavior for duplicate `issuedTo` is visible or explained in the UI (e.g. toast: “Existing invitation for this recipient”).
6. **No email** sending required for acceptance.
7. **`GET /auth/invitations`** has **no** query parameters; **all** invitation list filtering (search on issued-to text, channel, claimed, user type, cohort, etc.) is **client-side** on the returned `items`. No dedicated channels endpoint (§5.1).
8. The page uses a **three-tab** UI (**Users** default, **Invitations** second, **Cohorts** third) on a **single** admin route (§7).
9. **Users** tab shows a **read-only** list from **`GET /auth/admin/user-profiles`** with the fields in §5.5 / §7.3 (including **cohort**) and a visible row count.
10. **Cohorts** tab: admin can **create** cohorts (`key` + optional `description`), **list** them, **edit description**, and **delete** only when not referenced (**409** otherwise).
11. **Issue with cohort:** Admin can select a cohort when issuing an invite; **sign-up with that code** results in **`user_profiles.cohort_id`** matching the invitation’s cohort (verified in DB or Users tab).

---

## 11. Dependencies and references

- Phase 2 implementation: [p2_pr03 — Invitation code issuance and claim service](../phase-2-authentication-segmentation/p2_pr03-invitation-code-issuance-and-claim-service.md)
- CLI path: [p2_pr04 — Manual invitation code generation script](../phase-2-authentication-segmentation/p2_pr04-manual-invitation-code-generation-script.md)
- Admin mutation pattern: [p5 admin runtime theme spec](../phase-5-visual-editing/p5_admin-runtime-theme-spec.md) (same `require_admin_managed_auth` pattern)
- Metrics context: [Enhanced user monitoring and cost tracking](./enhanced-user-monitoring-and-cost-tracking.md) (labeling usage by `cohort_key` once implemented)

---

## 12. Implementation checklist (shipped 2026-03-22)

- [x] **Supabase migration:** `user_cohorts` table; `cohort_id` on `invitation_codes` and `user_profiles` (§3.4)
- [x] **Claim path:** invitation claim / claim-for-signup stamps `cohort_id` on profiles from the invitation (§3.4)
- [x] `SupabaseAuthRepository`: list invitations (with cohort), list user profiles for admin (cohort join + Auth email enrichment), conditional delete, cohort CRUD helpers
- [x] `GET /auth/invitations`, `DELETE /auth/invitations/{id}`, `GET /auth/admin/user-profiles`, **`GET|POST|PATCH|DELETE /auth/admin/cohorts`**, extend **`POST /auth/invitations`** with `cohortId` + models
- [x] Tests in `test_invitation_routes.py`, `test_supabase_auth_repository.py`, etc.
- [x] `notion_pipeliner_ui`: `api.ts`, **`/admin/users`** with **Users | Invitations | Cohorts** tabs (Users default), shell nav, admin gate; follow-ups (readability modal, parity, email UX) tracked in sibling beta docs / `work-log.md`
- [x] Manual smoke recommended: **Cohorts** — create cohort; **Invitations** — issue with cohort → sign up → **Users** shows cohort + email; unclaimed invite revoke; cohort delete blocked when referenced

---

## 13. Services to restart after implementation

Per deployment mapping: backend route/repo changes require **API** restart; UI changes require **frontend** dev server / static deploy. **Supabase:** apply migration (`make supabase-migrate` or project workflow) before or with deploy — **new tables and columns** (§3.4).
