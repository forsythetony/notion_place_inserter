# Invitations tab — readability and accessibility polish

**Status:** Complete on 2026-03-22 (see `work-log.md` Log).  
**Audience:** Frontend engineers; product for scope confirmation  
**Primary code:** [`notion_pipeliner_ui/src/routes/AdminUsersPage.tsx`](../../../../../notion_pipeliner_ui/src/routes/AdminUsersPage.tsx) (Invitations tab: issue form, filters, `InvitationCard` list), styles under [`.admin-invite-*` / `.admin-users-*`](../../../../../notion_pipeliner_ui/src/App.css) in [`App.css`](../../../../../notion_pipeliner_ui/src/App.css)

---

## Problem

The **Invitations** tab on `/admin/users/invitations` presents the right **information** (issue workflow, client-side filters, per-invitation cards with code, status, issued-to, cohort/channel badges, timestamps, claimed-by user id, revoke for unclaimed rows) but the UI reads **too small** for comfortable daily use: field labels, metadata labels, monospace ids, and badges sit at **~10–13px**, with **dense horizontal grids** on wide screens. Operators should not need to lean in or zoom the browser to scan codes and statuses.

**Goal:** Keep the **same fields and facts** on screen; raise **legibility**, **tap/click target** sizes, and **contrast** so the page feels like other management surfaces, without turning the tab into a sparse marketing layout.

---

## Current implementation notes (baseline)

Typography is driven mostly by `App.css` (not ad-hoc inline styles in the tab):

| Area | Approx. sizes today | Notes |
|------|---------------------|--------|
| Section labels (“FILTER”, block titles) | **11px**, uppercase | `.admin-invite-section-label`, `.admin-invite-filter-note` |
| Form field labels (issue + filter rows) | **11px** | `.admin-invite-field` |
| Inputs / selects | **13px**, height **32px** | `.admin-invite-field input, select` |
| Primary action (“Issue invitation”) | **13px**, height **32px** | `.admin-invite-submit` |
| List count (“Showing n of m”) | **12px** | `.admin-invite-count` |
| Card: badges (user type, cohort, channel) | **11px** | `.admin-invite-badge` |
| Card: invite code pill | **11px** monospace | `.admin-invite-code-pill` |
| Card: status (“Claimed” / “Pending”) | **12px** | `.admin-invite-card__status` |
| Card: slot labels (“ISSUED TO”, “ISSUED”, …) | **10px**, uppercase | `.admin-invite-slot__label` |
| Card: slot values (email, timestamps) | **12px** | `.admin-invite-slot__value` |
| Card: full user id | **11px** monospace, `word-break: break-all` | `.admin-invite-uuid` |
| Copy buttons | `btn-small` (shared compact button) | Paired with small type |

Section titles use **1.125rem** (`.admin-users-section-title`); helper copy uses **0.8125rem** (`.admin-users-muted`) — closer to acceptable body-secondary but still on the small side for long sentences.

---

## Design principles

1. **No information removal** — Do not hide cohort, channel, timestamps, or ids by default. Prefer **larger type**, **clearer hierarchy**, and **smarter truncation** over removing columns or collapsing sections.
2. **Minimum readable body scale** — Treat **~14px** (0.875rem at 16px root) as the **floor** for interactive labels and primary reading text on this tab; **avoid 10px** for any user-facing copy except optional fine print (and even then prefer 12px).
3. **Labels vs values** — Metadata labels should be **smaller than values**, not the same size or larger in visual weight. Today uppercase **10px** labels compete poorly with **12px** values; bump **values** more than **labels**, or move labels to **sentence case** at **12px** so they stay scannable without shouty caps.
4. **Contrast** — Secondary text uses `var(--text-secondary)` on dark surfaces; any size reduction must still meet **WCAG 2.1 AA** for normal text (4.5:1). If contrast fails after enlarging type, adjust tokens in the runtime theme path, not one-off hex in this tab only.
5. **Targets** — Interactive controls (inputs, selects, copy, revoke) should align with **44×44px** minimum hit areas where practical (padding + min-height), or at least **40px** height for desktop-first admin UIs.
6. **Responsive density** — Wide single-row toolbars are efficient but shrink text mentally; at **medium breakpoints**, prefer **two rows** or a **stacked** layout with **wider inputs** rather than shrinking font sizes further.

---

## Recommended changes (implementation-ready)

### A. Issue form and filter toolbar

- Raise **input/select font-size** from 13px toward **15–16px**; increase **min-height** to **40px** (or 44px) and padding accordingly.
- Raise **field labels** from 11px to **12–13px**; consider **sentence case** (“Issued to”) instead of all-caps micro labels.
- Keep the **grid** but allow **more vertical gap** between label and control so the block breathes (e.g. `gap` on `.admin-invite-field` from 4px → 6–8px).
- **Section labels** (“Filter”) — either match **body-secondary at 12px** without aggressive uppercase, or keep uppercase but at **12px minimum** and track letter-spacing slightly tighter so line length stays stable.
- **“Filters apply in the browser only”** — keep as secondary helper at **12px+**, not 11px.

### B. Invitation cards

- Increase **card padding** (e.g. 8px 12px → **12px 16px**) and **list gap** between cards (e.g. 6px → **10–12px**).
- **Badges:** bump to **12–13px**; keep color semantics; slightly increase **padding** so pills feel tappable if they ever become interactive.
- **Invite code pill:** increase to **13–14px**; maintain monospace; ensure the **Copy** button scales with `btn-small` → default or a dedicated **compact-but-not-tiny** size for this surface only.
- **Status row:** **13–14px** for “Claimed” / “Pending”; slightly enlarge status dot if needed for balance.
- **Slot labels:** replace **10px uppercase** with **12px** and **sentence case** (“Issued to”, “Claimed by”) OR **12px** uppercase with reduced letter-spacing — **never 10px** for primary structure labels.
- **Slot values (email, dates):** **14px** line-height ~1.45; preserve `word-break` for long emails.
- **Claimed-by user id:** Showing the **full UUID** at 11px is correct for power users but harsh. Options that preserve information:
  - **Truncate visually** to `truncateId`-style display (e.g. first 8 + … + last 4) at **13–14px**, with **title** / **tooltip** / **copy** still holding the full id (already partially aligned with Users table patterns).
  - Keep full string only if width allows **14px** monospace without horizontal scroll; otherwise truncate + copy is better than microscopic full string.

### C. Cross-cutting

- **Buttons:** Audit `btn-small` usage on this tab; if copy/revoke stay “small,” define **`admin-invite-*` button** modifiers that are one step up from global `btn-small` so the tab can diverge without changing every page.
- **Focus states:** Ensure enlarged controls still show **visible `:focus-visible` rings** (style guide / existing `--focus` tokens).
- **Users and Cohorts tabs** on the same page share `.admin-users-table`, `.admin-users-field`, etc. — either scope invitation-specific bumps under `.admin-users-page` + invitations route wrapper or introduce a **shared “admin density”** token so the **Users/Cohorts** tables gain the same readability in one pass (preferred for consistency).

---

## Out of scope

- **Server-side filtering**, pagination, or API changes — not required for this UX pass.
- **Replacing cards with a data grid** — optional future; this doc assumes **card layout** stays.
- **Full WCAG audit** of the entire app — this doc targets **this tab** first; patterns can feed [`beta-ui-general-polish.md`](./beta-ui-general-polish.md).

---

## Acceptance criteria

1. No **primary** label or value on the Invitations tab is rendered smaller than **12px** except optional tertiary hints (if any), and **main content** (inputs, card values, code pill) is **≥ 14px** where feasible.
2. Issue form and filter controls meet **40px+** vertical touch/click height or equivalent padded hit area without reducing label legibility.
3. **Claimed-by user id** remains **copyable in full**; if truncated in the layout, full id is available via **title** and/or **copy** affordance.
4. Visual hierarchy reads as **value > label** for each slot; filter and issue sections remain **scannable at arm’s length** on a laptop display at **100% zoom**.
5. **Contrast** of secondary text against backgrounds meets **AA** for the sizes used (verify with admin default theme and one dark runtime theme preset if applicable).

---

## References

- Parent feature spec: [Admin users, invitations & cohorts UI](./admin-invitation-management-ui.md)
- Cross-page polish (sibling): [Beta UI general polish](./beta-ui-general-polish.md)
- Implementation canon: [`notion_pipeliner_ui/styleguide/`](../../../../../notion_pipeliner_ui/styleguide/README.md)
