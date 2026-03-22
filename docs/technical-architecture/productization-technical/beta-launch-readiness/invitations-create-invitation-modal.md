# Invitations — “Create Invitation” modal + primary button

**Status:** Complete on 2026-03-22 (see `work-log.md` Log).  
**Audience:** Frontend engineers; product for scope confirmation.  
**Primary code (when implemented):** [`notion_pipeliner_ui/src/routes/AdminUsersPage.tsx`](../../../../../notion_pipeliner_ui/src/routes/AdminUsersPage.tsx) (`AdminUsersInvitationsTab`), shared modal styles (likely [`App.css`](../../../../../notion_pipeliner_ui/src/App.css) under `.admin-invite-*` or a small dedicated component file).

---

## Summary

Replace the **inline “Issue new invitation” form** on the **Invitations** tab with:

1. A single, obvious **primary control** on the page: a button labeled **Create Invitation** (see §Naming for title vs sentence case).
2. A **modal dialog** that contains the **same fields and behavior** as today’s issue form: issued-to label, channel, user type, cohort, submit, and cancellation.

**Backend and API are unchanged:** `POST /auth/invitations` with `userType`, optional `issuedTo`, `platformIssuedOn`, `cohortId` — see [`app/routes/invitations.py`](../../../../app/routes/invitations.py) and client [`issueAdminInvitation`](../../../../../notion_pipeliner_ui/src/lib/api.ts).

---

## Problem

Today the Invitations tab leads with a **full-width inline form** (“Issue new invitation”) above filters and the card list. That is correct functionally but:

- Competes visually with **filters** and the **list**, so the page feels like three stacked toolbars before you see history.
- Does not match a common **task-oriented** pattern: *open dialog → fill → confirm → return to list*.

Operators still need the same inputs; the change is **layout and focus**, not data model.

---

## Current baseline (to preserve)

Implemented in `AdminUsersInvitationsTab`:

| Field | Maps to API |
|-------|-------------|
| Issued to (label / email) | `issuedTo` (optional) |
| Channel | `platformIssuedOn` (optional) |
| User type | `userType` (required; `ADMIN` \| `STANDARD` \| `BETA_TESTER`) |
| Cohort | `cohortId` (optional UUID; “None” = omit) |

Submit calls `issueAdminInvitation(...)`; success shows a **last-issued** block with **code** + **Copy**, and idempotent re-issue copy when the backend returns the existing row for the same `issuedTo` (see §Success messaging).

**Do not regress:** cohort list still comes from `listAdminCohorts`; after issue, list refresh should include the new or updated row.

---

## Target UX

### Page layout (Invitations tab)

1. **Section header row** — Keep the **Invitations** `<h2>` (existing `admin-users-section-title`).
2. **Action** — To the right of the title (or directly under it on narrow viewports), a **primary** button **Create Invitation** (see §Placement).
3. **Remove** the inline **Issue new invitation** card and its **Issue invitation** submit from the main scroll area (filters + list move up).

Optional: one line of muted helper copy under the header, e.g. *Issue a code for a beta participant; copy or share the code manually.* (Only if it does not duplicate the page-level description.)

### Modal: structure

- **Title:** “Create Invitation” (or “Issue invitation” if product prefers verb parity with API docs — pick one and use consistently with the button).
- **Body:** Form fields **mirror** the current inline form (same labels, placeholders, options, validation).
- **Footer:**
  - **Primary:** “Create Invitation” / “Issue” — submits; disabled while request in flight (`busy`).
  - **Secondary:** “Cancel” — closes without issuing; discards unsaved field edits unless we explicitly add a dirty confirm (v1: **no** dirty prompt; optional follow-up).

### Modal: open/close

- **Open:** Click **Create Invitation**; move focus to the first focusable control in the dialog (or the dialog title container if using `aria-labelledby`).
- **Close (cancel):** Cancel button, **Escape** key, click **backdrop** (if enabled — see §Accessibility).
- **Close (success):** Either **auto-close** after a short success state that shows the code + copy, or **keep open** with an inline success panel and a **Done** / **Close** that dismisses. **Recommendation:** show **code + Copy** **inside the modal** on success, then **Done** closes and refreshes list; avoids losing the code if the user blurs. Alternatively match current behavior: close modal and show **last issued** below the button area — but that is less discoverable if the modal is gone. Prefer **success inside modal** or **toast + list refresh** so the code is never only in a transient toast.

### Success messaging

Preserve today’s semantics:

- Show the **20-character code** with **Copy**.
- If the backend indicates **idempotent reissue** (same `issuedTo`), show the existing explanatory note (see current `lastIssue.note`).

### Placement of the primary button

- **Desktop:** Align **Create Invitation** with the section header — e.g. flex row: title left, button right (`flex` + `justify-content: space-between` on a wrapper), consistent with other admin surfaces.
- **Mobile:** Stack: title, then full-width button, then errors/alerts.

---

## Naming and copy

| Element | Label |
|---------|--------|
| Page button | **Create Invitation** |
| Modal title | **Create Invitation** (same as button action) |
| Primary modal action | **Create Invitation** (or **Issue invitation** if matching API wording — avoid mixing “Create” in one place and “Issue” in another without reason) |

**Recommendation:** use **Create Invitation** everywhere in the UI for this flow; the API remains “issue” in code comments only. If the style guide prefers sentence case for buttons, **Create invitation** is an acceptable alternative — keep **one** convention across button, title, and primary action.

---

## Accessibility

- **Role:** `role="dialog"` with **`aria-modal="true"`** on the dialog container.
- **Label:** `aria-labelledby` pointing at the modal title id, or `aria-label` if the title is decorative-only.
- **Focus:** On open, move focus into the dialog; on close, **return focus** to the **Create Invitation** trigger.
- **Escape:** Close the dialog (same as Cancel).
- **Backdrop:** If clickable to dismiss, ensure that does not fire when clicking inside the dialog panel.
- **Stacking:** Render via **`createPortal`** to `document.body` (same pattern as [`BindingPickerModal`](../../../../../notion_pipeliner_ui/src/components/BindingPickerModal.tsx)) to avoid clipping and z-index issues.
- **Readability:** Follow minimum type and control sizes from [Invitations tab readability & accessibility](./invitations-tab-readability-and-accessibility.md) inside the modal.

---

## Visual styling

- Reuse **`.admin-invite-field`**, inputs, selects, and button tokens where possible so the modal matches the rest of the tab without a second design system.
- Modal chrome: **backdrop** scrim (reuse app overlay tokens if present), **panel** with padding and max-width (e.g. `min(32rem, 100vw - 2rem)`), **rounded** corners consistent with other admin dialogs.

---

## Implementation notes

- **State:** Lift the same form state (`issuedTo`, `platformIssuedOn`, `userType`, `cohortId`) into the tab or a small `CreateInvitationModal` component; reset fields when the modal opens (or when it closes after success — define one behavior and stick to it).
- **Errors:** `actionError`/`management-inline-alert` can stay **above the tab content** or move **inside the modal** for issue failures; **inside the modal** is preferred so the user sees the error next to the form.
- **Loading:** Disable form + primary button while `busy`; consider optional `aria-busy` on the dialog.
- **Tests:** Extend [`router.test.tsx`](../../../../../notion_pipeliner_ui/src/test/router.test.tsx) or add a focused test: open Invitations tab → **Create Invitation** opens dialog → required fields → submit mocks `issueAdminInvitation`.

---

## Out of scope (v1)

- **Batch invite** or CSV upload in the modal.
- **Email delivery** of codes from the app.
- **Editing** an invitation after creation.
- **Backend** changes to `POST /auth/invitations` or validation rules.

---

## Acceptance criteria

1. The Invitations tab **no longer** shows the full inline **Issue new invitation** form in the main layout; **filters and list** are the primary scroll content after the header + **Create Invitation** button.
2. **Create Invitation** opens a **modal** with the **same four fields** and **cohort** behavior as the current implementation.
3. Submit uses **`issueAdminInvitation`** and **refreshes** the invitation list on success; **code** and **Copy** are available (in-modal or immediately after close, without losing the code).
4. **Cancel**, **Escape**, and (if implemented) **backdrop** close the modal without issuing; focus returns to the trigger.
5. **WCAG:** Dialog role, focus trap, visible focus, and labels associated with inputs; no new text smaller than the readability spec’s floors for primary content.

---

## References

- Parent feature spec: [Admin users, invitations & cohorts UI](./admin-invitation-management-ui.md)
- Readability baseline: [Invitations tab readability & accessibility](./invitations-tab-readability-and-accessibility.md)
- Modal pattern reference: [`BindingPickerModal`](../../../../../notion_pipeliner_ui/src/components/BindingPickerModal.tsx)
