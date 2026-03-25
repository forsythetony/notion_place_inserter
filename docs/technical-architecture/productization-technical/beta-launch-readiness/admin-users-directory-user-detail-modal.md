# Admin Users directory — user detail modal

**Status:** Not started — design for implementation.  
**Goal:** Beta user launch — operators can open a **single modal** from the **Users** tab (`/admin/users` → **Users**) to see **everything on the current user card**, plus **limits**, **last sign-in**, and **EULA acceptance** (including whether the user is **behind** the currently published EULA).

**Related docs:** [Admin invitation management UI](./admin-invitation-management-ui.md) (admin shell), [Global and per-user resource limits](./global-and-per-user-resource-limits.md), [EULA versioning, acceptance, and admin management](./eula-versioning-and-acceptance.md).

---

## 1. Summary

Today each row in the Users directory is a **`UserDirectoryCard`** (`notion_pipeliner_ui/src/routes/AdminUsersPage.tsx`): user type, email, cohort pill, copyable ids (user, invitation code, cohort), created/updated timestamps, and a **Limits** button that opens **`UserLimitsModal`** (full limits + usage + edit).

This spec adds a **primary interaction**: **click the user (card or a clear affordance)** to open a **user detail modal** that:

1. Repeats **all fields currently visible on the card** (same layout patterns / components where practical).
2. Adds a **Limits** section — at minimum **read-only effective caps + usage** consistent with the top of `UserLimitsModal`; optionally a **Manage limits** control that opens the existing `UserLimitsModal` (same behavior as today’s footer button) to avoid duplicating edit logic.
3. Adds **Last sign-in** — **not** in our DB today; must come from **Supabase Auth** (service role / admin API), see §4.
4. Adds **EULA** — **accepted version** and **acceptance time** from `user_profiles` (already stored), plus a clear **vs published** indicator so admins see if the user is **on the current published EULA** or **behind** (see §5).

Authorization stays **`require_admin_managed_auth`** (same as other `/auth/admin/*` routes).

---

## 2. Current implementation (baseline)

### 2.1 Frontend — card contents

`UserDirectoryCard` renders:

| Area | Content |
|------|---------|
| Header | User type badge, email, cohort badge (if any) |
| Body | User id, invitation code id, cohort id (if any), **Created**, **Updated** |
| Footer | **Limits** → `UserLimitsModal` |

Relevant code: `UserDirectoryCard` and `UserLimitsModal` in [`notion_pipeliner_ui/src/routes/AdminUsersPage.tsx`](../../../../../notion_pipeliner_ui/src/routes/AdminUsersPage.tsx).

### 2.2 Backend — list profiles

- **Route:** `GET /auth/admin/user-profiles` — [`app/routes/auth_admin.py`](../../../../../app/routes/auth_admin.py) (`list_user_profiles_admin`).
- **Serialization:** `_profile_row_to_item` already returns **`eulaVersionId`**, **`eulaAcceptedAt`**, plus profile timestamps and cohort/invite ids.
- **Email:** `SupabaseAuthRepository.list_user_profiles_for_admin` merges **`email`** from **`auth.admin.list_users`** (paginated) into each row — same pattern as §4 for extending Auth-derived fields.

### 2.3 Gap — TypeScript client

`AdminUserProfileItem` in [`notion_pipeliner_ui/src/lib/api.ts`](../../../../../notion_pipeliner_ui/src/lib/api.ts) **does not declare** `eulaVersionId` / `eulaAcceptedAt` even though the API returns them. Implementation should **extend the type** (and any mocks/tests) so the modal can show EULA without ad-hoc casting.

---

## 3. UX and UI structure

### 3.1 Entry point

- **Click target:** the **card** (or a **“View details”** / primary row control — product choice). Using the whole card matches “clicking on the user”; ensure **Limits** remains a distinct control so power users do not lose the direct path to the limits editor.
- **Modal:** Reuse existing overlay/dialog patterns (`management-modal-*`, `createPortal` to `document.body`) already used by `UserLimitsModal` and other admin modals for consistency and focus management.

### 3.2 Sections (recommended order)

1. **Header** — Email (or “—”), user type badge, cohort badge; optional subtitle with user id (copyable).
2. **Profile** — Same slots as the card: invitation code id, cohort id, created, updated (reuse `CopyableId`, `formatProfileTimestamp`, `userTypeDisplayName` helpers).
3. **Authentication** — **Last sign-in** (ISO or formatted local time; “Never” if null — e.g. user created but never completed a password session).
4. **EULA** — Accepted **version label** (resolved server-side, see §5), **accepted at**, and a **status** pill:
   - **Current** — accepted version id equals **published** EULA id.
   - **Behind** — published EULA exists and user’s `eula_version_id` is non-null and **not equal** to published id (user accepted an older published version before a new publish).
   - **Unknown / not on file** — `eula_version_id` is null (legacy or non-signup path), or published EULA missing (edge case).
5. **Limits** — Summary table: usage vs effective caps (mirror `UserLimitsModal` usage table). **Edit limits** → opens existing `UserLimitsModal` (or inline expand — prefer **one** limits editor to avoid drift).

### 3.3 Accessibility

- `role="dialog"`, `aria-modal="true"`, labelled title, **Escape** closes, focus trap consistent with other admin modals.
- If the card is fully clickable, ensure **Limits** uses `stopPropagation` so activating Limits does not open the detail modal (or use separate buttons only).

---

## 4. Last sign-in — backend design

**Source of truth:** Supabase Auth user record (`last_sign_in_at` — naming may vary slightly by client version; normalize to ISO string in the API response).

**Options:**

| Approach | Pros | Cons |
|----------|------|------|
| **A. Extend profile list** — When building the email map in `list_user_profiles_for_admin`, also stash `last_sign_in_at` per user in a parallel map | One round-trip for directory + modal if modal uses list data only | List payload grows; still need **per-user** fetch if we open modal without full list in memory |
| **B. New `GET /auth/admin/users/{userId}`** — Returns merged **profile row** + **Auth user** fields (`email`, `last_sign_in_at`, …) + **EULA enrichment** + optional **published EULA id** for comparison | Clean contract for the modal; single source for “detail” | Extra request when opening modal |
| **C. Add fields only to list response** — Add `lastSignInAt` to each item in `GET /auth/admin/user-profiles` | No new route | Large directory = heavier Auth iteration (already one full `list_users` pass for emails) |

**Recommendation:** **B** for clarity and future fields (phone, providers, banned — if ever needed), **or** augment **list** (**A/C**) if we want **zero** extra request and are willing to extend `_auth_user_id_to_email_map` into `_auth_user_id_to_metadata_map` returning `{ email, last_sign_in_at }` in one paginated loop (best efficiency vs duplicate `get_user` N times).

**Anti-pattern:** N+1 `get_user_by_id` calls from the frontend for each card — avoid.

**API shape (illustrative):**

```json
{
  "userId": "uuid",
  "profile": { "...": "same as list item / _profile_row_to_item" },
  "auth": {
    "email": "user@example.com",
    "lastSignInAt": "2026-03-23T12:00:00+00:00"
  },
  "eula": {
    "acceptedVersionId": "uuid",
    "acceptedAt": "2026-03-20T10:00:00+00:00",
    "acceptedVersionLabel": "2026-03-20",
    "publishedVersionId": "uuid",
    "publishedVersionLabel": "2026-03-23",
    "status": "current" | "behind" | "no_acceptance_on_file" | "published_missing"
  }
}
```

Implement `eula.status` in the service layer so the UI stays dumb.

---

## 5. EULA — “behind” semantics

**Published EULA:** At most **one** row with `status = 'published'` in `eula_versions` (enforced by partial unique index). Use existing `get_published_eula()` in [`SupabaseAuthRepository`](../../../../../app/services/supabase_auth_repository.py).

**Rules:**

- **`current`** — `user_profiles.eula_version_id` is not null **and** equals `published.id`.
- **`behind`** — `published` exists, `user_profiles.eula_version_id` is not null, **and** `user_profiles.eula_version_id != published.id`.  
  *Interpretation:* After ops publish a **new** EULA, existing users remain on the version they accepted at signup until a **re-acceptance** flow exists (if product adds one later). “Behind” means **not on today’s published revision**.
- **`no_acceptance_on_file`** — `eula_version_id` is null (legacy / admin-created profile).
- **`published_missing`** — No published EULA in DB (should be rare; show copy-safe warning).

**Display:** Show **accepted** `version_label` (from `eula_versions` join on `user_profiles.eula_version_id`) and **published** `version_label` for comparison. Do **not** infer order by label string; **equality** to published id is enough.

---

## 6. Limits in the modal

**Read path:** Reuse **`GET /auth/admin/limits/users/{userId}`** — already implemented; [`getAdminUserLimitsDetail`](../../../../../notion_pipeliner_ui/src/lib/api.ts) matches backend.

**Write path:** Keep **`UserLimitsModal`** as the single editor; from the detail modal, **“Edit limits…”** opens it (nested modal or close detail first — **prefer sequential**: close detail → open limits, **or** stack with clear focus order; simplest is **replace** content or **two-step** to avoid double overlay).

---

## 7. Frontend modules

| Piece | Action |
|-------|--------|
| `AdminUsersPage.tsx` | State: `detailUserId \| null`; open on card click; render `UserDetailModal` |
| New `UserDetailModal` (same file or `components/AdminUserDetailModal.tsx`) | Fetch detail endpoint; sections §3.2 |
| `api.ts` | Types for detail response; `getAdminUserProfileDetail(accessToken, userId)` |
| `App.css` | Only if new layout classes needed; prefer reusing `admin-invite-*` / `admin-users-*` |

---

## 8. Backend modules

| Piece | Action |
|-------|--------|
| `auth_admin.py` | New `GET /auth/admin/users/{user_id}` (or `/user-profiles/{user_id}` — align with REST style) |
| `SupabaseAuthRepository` | Helper: fetch Auth user fields for one id; optional: enrich EULA labels via `get_eula_version_by_id` |
| Tests | Route test: admin OK, non-admin 403; EULA status matrix; last sign-in null vs set |

---

## 9. Acceptance criteria

- [ ] Clicking a user in the Users directory opens a modal containing **at least** the same information as **`UserDirectoryCard`**.
- [ ] Modal shows **limits summary** (usage + effective caps) and provides a path to the **existing** limits editor.
- [ ] Modal shows **last sign-in** from Supabase Auth (or “Never” / equivalent).
- [ ] Modal shows **EULA version accepted** and **acceptance time**, and clearly indicates **current vs behind** vs **no acceptance on file**.
- [ ] `AdminUserProfileItem` (or successor) **includes EULA ids** returned by the list API for consistency.
- [ ] Automated tests: API unit/route tests for new endpoint; optional React test for modal open/close.

---

## 10. Out of scope (this iteration)

- Forcing users to re-accept EULA from the app (only **visibility** for admins here).
- Editing profile rows (still read-only admin directory).
- Exposing full Auth audit log or session list.
