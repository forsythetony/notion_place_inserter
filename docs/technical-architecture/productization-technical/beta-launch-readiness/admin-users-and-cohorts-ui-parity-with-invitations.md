# Admin Users & Cohorts tabs — UI parity with Invitations

**Status:** **Complete on 2026-03-22** (Users + Cohorts card UI, modals, `CopyableId`, CSS)  
**Primary code:** `notion_pipeliner_ui` — `src/routes/AdminUsersPage.tsx` (`InvitationCard`, `UserDirectoryCard`, `CohortCard`, tabs), `src/components/CreateInvitationModal.tsx`, `src/components/CreateCohortModal.tsx`, `src/components/EditCohortDescriptionModal.tsx`, `src/components/CopyableId.tsx`, `src/App.css`  
**UI style guide:** `notion_pipeliner_ui/styleguide/` — see [Style guide updates](#style-guide-updates-notion_pipeliner_uistyleguide).  
**Backend:** No API changes required for this UI pass (existing `listAdminUserProfiles`, `listAdminCohorts`, `createAdminCohort`, etc.).

## Purpose

Align the **Users** and **Cohorts** admin tabs with the **Invitations** tab: card-based rows, two-column detail layout, colored pills for categorical fields, copyable full identifiers, filter tooling where useful, and **no inline create/edit forms** on the page surface (creation and primary edits happen in modals).

This doc captures the target design so implementation can mirror the established invitations patterns without re-deriving layout each time.

---

## Reference implementation: Invitations tab

The Invitations tab (`AdminUsersInvitationsTab` + `InvitationCard` in `AdminUsersPage.tsx`) already encodes the patterns we want to reuse:

| Pattern | Implementation |
|--------|------------------|
| Section header + primary action | `admin-invite-section-header` with title and **Create Invitation** opening `CreateInvitationModal` |
| List container | `admin-invite-list` of `article.admin-invite-card` |
| Header row | Left: **user type** + optional **cohort** + **channel** badges (`admin-invite-badge`, variant classes). Right: **invitation code** in `admin-invite-code-pill`, **Copy**, vertical rule, **Claimed / Pending** status |
| Two-column body | `admin-invite-card__body`: grid with central `admin-invite-card__vdiv`; columns `admin-invite-card__col--identity` vs `admin-invite-card__col--temporal` |
| Labeled slots | `admin-invite-slot` / `admin-invite-slot__label` / `admin-invite-slot__value` |
| Copy affordance | `admin-invite-copy-btn` with ephemeral **Copied** state |
| Filters | `admin-invite-tools` with browser-side filters and count |

**Identifiers (shipped):** Invitation codes and claimed-user UUIDs use full text with wrap + **Copy** (`CopyableId` / `.admin-invite-uuid`); cohort/channel badges and code pill allow wrapping (no ellipsis truncation for display).

---

## Product requirements (locked)

1. **UUIDs and invitation codes** — Never visually truncated; always copyable (wrap / break long lines; copy copies full string).
2. **Colored pills** — Use the same badge system for **user type** (and cohort/channel where applicable), reusing `userTypeBadgeClass` / `admin-invite-badge--*` conventions.
3. **Two-column layout** — Per-row card body: identity / linkage in one column; timestamps (and secondary metadata) in the other, with the same grid + divider pattern as invitations.
4. **Modals only for mutation** — No inline creation (or inline primary edit) on the tab. Cohort **create** moves off the inline form; cohort **edit description** remains modal-based but should use the same modal shell/patterns as `CreateInvitationModal` (focus trap, escape, return focus).

---

## Users tab (`AdminUsersDirectoryTab`)

### Current state

- Read-only **HTML table** (`admin-users-table`): User ID and invitation code ID shown with `truncateId()`; user type as plain text; no filters; no card layout.

### Target state

- **Card list** parallel to `InvitationCard`: e.g. `UserDirectoryCard` (or shared `AdminEntityCard` wrapper) using the same BEM block or a scoped alias (e.g. `admin-user-card` extending shared layout classes) to avoid one-off CSS drift.
- **Header row**
  - **Pills:** `userTypeBadgeClass(row.userType)` + human-readable label via `userTypeDisplayName` (already defined in `AdminUsersPage.tsx`).
  - **Cohort:** If `cohortKey` present, reuse `admin-invite-badge--cohort` (show **full** key; remove `truncateCohortLabel` for this surface — or keep truncation only in ultra-dense contexts; default per requirements is **no truncation**).
  - Optional: secondary line or pill for “directory” read-only hint is **not** required; keep copy minimal.
- **Body — two columns**
  - **Column A (identity / linkage):**
    - **User ID** — Full UUID in monospace, `word-break` / `overflow-wrap`, with **Copy** (same feedback pattern as invitations).
    - **Invitation code ID** — If present: full UUID (or opaque id) + Copy; if absent: muted “—” or “No linked invitation”.
    - **Cohort ID** (if `cohortId` is non-null and distinct from display needs) — Optional slot; if shown, full id + Copy for admin debugging.
  - **Column B (temporal):**
    - **Created** / **Updated** using `formatInviteTimestamp` or shared `formatDt` consistently (pick one family for admin cards; invitations use compact `formatInviteTimestamp` for issued/claimed).
- **Toolbar (optional but recommended for parity):** Lightweight `admin-invite-tools`-style block:
  - Search (e.g. substring on `userId`, `cohortKey`, `invitationCodeId` as stringified).
  - Filter by **user type** (reuse `USER_TYPES`).
  - Filter by **cohort key** (union of keys from loaded rows).
  - `Showing X of Y` count.
- **No create action** — Directory remains read-only; no modal for “create user” unless product adds that later.

### CSS / a11y

- Reuse `admin-invite-card__body` grid or extract shared class names into a neutral block (e.g. `admin-admin-card__body`) used by invitations, users, and cohorts to prevent three diverging grid definitions.
- Update **copyable id** styles: replace ellipsis truncation with wrapping (see [CSS](#css-changes)).

---

## Cohorts tab (`AdminUsersCohortsTab`)

### Current state

- **Inline form** (`admin-users-issue-form`) for new cohort key + description + submit — violates “no inline creation”.
- **Table** listing key, description, dates, row actions.
- **Edit description** already in a modal overlay (`admin-users-modal-overlay`); **Delete** uses `window.confirm`.

### Target state

- **Section header** matching invitations: title **Cohorts** + primary **Create cohort** button opening a new **`CreateCohortModal`** (props: `open`, `onClose`, `accessToken`, `onSuccess`, `returnFocusRef`). Form fields: key (required), description (optional). On success: call existing `createAdminCohort` + refresh list + close + optional success toast/inline message.
- **Remove** the inline `form` block entirely.
- **List:** Replace table with **cohort cards** (e.g. `CohortCard`) using the same outer shell as invitation/user cards:
  - **Header:** cohort **key** as a pill (`admin-invite-badge--cohort` or dedicated `admin-cohort-key-pill`), optional small meta (created) if space allows.
  - **Body — two columns:**
    - **Column A:** Full **cohort id (UUID)** with Copy + **description** (or “No description”) as slot text.
    - **Column B:** **Created** / **Updated** timestamps.
  - **Footer:** **Edit description** (opens existing edit modal, refactored to shared modal component shell), **Delete** (keep confirm or move to destructive confirmation modal — confirm is acceptable for beta).
- **Edit description modal:** Refactor inline JSX into **`EditCohortDescriptionModal`** (or extend one `CohortModal` with mode `create` | `edit`) with the same focus/escape/return-focus behavior as `CreateInvitationModal`.

### API

- Unchanged: `createAdminCohort`, `updateAdminCohortDescription`, `deleteAdminCohort`, `listAdminCohorts`.

---

## Invitations tab — alignment fixes

To satisfy global rules for identifiers:

1. **`InvitationCard`:** Stop using `truncateId(row.claimedByUserId)` for display; render the **full** UUID with wrapping + Copy.
2. **`admin-invite-uuid` in `App.css`:** Remove `overflow: hidden; text-overflow: ellipsis; white-space: nowrap` for copyable id lines; use `overflow-wrap: anywhere` or `word-break: break-all` with monospace stack.
3. **Cohort badge:** Either show full `cohortKey` or rely on wrapped pill text; avoid middle-ellipsis unless strictly necessary for layout (requirements: prefer full text).

---

## Identifiers: never truncated, always copyable

| Field | Display | Copy |
|-------|---------|------|
| Invitation code | Full text in pill / row; may wrap | Copies exact `code` |
| User id | Full UUID, wrap | Copies exact `userId` |
| Invitation code id (user row) | Full id | Copies exact `invitationCodeId` |
| Cohort id | Full UUID | Copies exact `id` |
| Cohort key | Full string | Optional copy button if admins need to paste into configs |

**Clipboard errors:** Mirror invitations: surface `actionError` or inline alert when `navigator.clipboard` fails (Users tab today silently ignores copy failure).

---

## Component decomposition (suggested)

| Component | Responsibility |
|-----------|----------------|
| `CopyableId` or inline pattern | Full-width monospace text + Copy + copied state; shared by all three tabs |
| `UserDirectoryCard` | One `AdminUserProfileItem` |
| `CohortCard` | One `AdminCohortItem` |
| `CreateCohortModal` | Create cohort; portal + focus trap pattern from `CreateInvitationModal` |
| `EditCohortDescriptionModal` | Edit description only (extract from current inline modal) |

Optional: extract **`AdminCardShell`** (header / body grid / footer slots) if duplication across `InvitationCard`, `UserDirectoryCard`, and `CohortCard` exceeds ~2 copies.

---

## Style guide updates (`notion_pipeliner_ui/styleguide/`)

Implementation tokens and admin-specific interaction patterns belong in the **UI repo style guide**, not only in `App.css` comments. This parity work must keep that canon in sync.

### Deliverables

1. **`styleguide/admin-management.md`** — Canonical spec for admin management UI: tabbed `/admin/users` layout, section headers, **entity cards** (two-column body, pills, slots), **copyable identifiers** (no ellipsis truncation; wrap + Copy + error surfacing), **browser-side filters**, and **modal-only** create flows. Include anti-patterns (inline create forms, silent clipboard failure). Cross-link to [components.md](../../../../../notion_pipeliner_ui/styleguide/components.md) for shared buttons/forms and to [color-and-theme.md](../../../../../notion_pipeliner_ui/styleguide/color-and-theme.md) for tokens; link back to this architecture doc for phased delivery. *(Initial version added with this spec; extend when implementation lands.)*
2. **`styleguide/README.md`** — Register `admin-management.md` in the master table so contributors discover it before changing admin screens.
3. **`styleguide/components.md`** — Under **Cards**, add a short **Admin entity cards** subsection pointing to `admin-management.md` so the general card spec and admin list-row pattern stay connected.

### When to edit the style guide

- **Whenever** shared class names change (e.g. extracting `admin-admin-card__*` from `admin-invite-card`), or new modal components ship (`CreateCohortModal`, etc.).
- **When** visual tokens for admin pills/copy buttons shift (document the mapping to Calm Graphite / semantic tokens per [color-and-theme.md](../../../../../notion_pipeliner_ui/styleguide/color-and-theme.md)).

### Repo boundary

- **`notion_place_inserter/docs/style/`** — Product direction and pre-token branding only (per `docs-placement.mdc`). **Concrete admin UI patterns** live under **`notion_pipeliner_ui/styleguide/`**.

---

## CSS changes

1. **Shared card layout** — Either document shared classes in `App.css` under a neutral prefix (`admin-admin-card`) or reuse `admin-invite-card` with modifiers (`admin-invite-card--user`, `--cohort`) to avoid parallel maintenance.
2. **Copyable identifiers** — New or adjusted utility, e.g. `.admin-copyable-id` / `.admin-invite-uuid--full`: no ellipsis; `font-family: var(--mono)`; wrap long tokens.
3. **Pills** — Continue using `admin-invite-badge--admin|beta|standard|cohort` for user type and cohort key where appropriate.

---

## Testing

- **`router.test.tsx` / admin tests:** Update selectors if headings or structure change; assert **Create cohort** opens modal, not inline form.
- **Snapshot / RTL:** Optional tests for `UserDirectoryCard` copy buttons (mock `clipboard.writeText`).
- **Manual:** Long UUIDs wrap without horizontal scroll; copy pastes full string; keyboard focus returns to trigger after modal close.

---

## Acceptance criteria

- [x] Users tab uses card layout with two-column body and user-type pills; no truncated UUIDs or invitation code ids; copy buttons work with user-visible error on failure.
- [x] Cohorts tab has **no** inline create form; **Create cohort** opens a modal; list is card-based with two columns; cohort UUID and key are fully visible and copyable as specified.
- [x] Invitations tab shows full claimed-user UUID (no ellipsis truncation) and aligns CSS with wrap behavior.
- [x] Visual and structural consistency with invitations (header / body / footer rhythm, spacing, typography).
- [x] No new backend endpoints required; existing admin API clients in `src/lib/api.ts` suffice.
- [x] `notion_pipeliner_ui/styleguide/admin-management.md` and index/README (and **Cards** pointer in `components.md`) updated to match shipped UI.

---

## Related docs

- [Invitations tab readability & accessibility](./invitations-tab-readability-and-accessibility.md)
- [Invitations — create invitation modal](./invitations-create-invitation-modal.md)
- [Admin invitation management UI](./admin-invitation-management-ui.md)
- UI style guide: [`notion_pipeliner_ui/styleguide/admin-management.md`](../../../../../notion_pipeliner_ui/styleguide/admin-management.md) (admin patterns; path assumes `notion_pipeliner_ui` is a sibling of `notion_place_inserter`)
