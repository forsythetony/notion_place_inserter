# p5_pr02 - App Navigation Shell and Authenticated Landing Flow

## Objective

Ship the app shell and navigation behavior: public entry with sign-in/sign-out affordances in the upper right, then authenticated redirect into the dashboard. Introduce persistent app layout primitives (left nav + top utility) used by later dashboard and editor pages.

## Scope

- Implement or harden a consistent top utility area with auth controls (`Sign In` / `Sign Out`) and app shell behavior
- Ensure route flow is deterministic:
  - signed-out user sees public/marketing context
  - signed-in user is redirected to `/dashboard`
- Introduce persistent app layout primitives (left nav + top utility) used by dashboard and editor routes
- Apply style guide tokens from p5_pr01 for shell styling

## Expected changes

- Shared layout component(s) for authenticated app shell (left nav + top bar)
- Header/top utility area with auth state-driven controls (Sign In / Sign Out)
- Route guards and redirect logic for auth state
- Dashboard route as authenticated landing page
- No page-specific one-off layout forks; shell reused by all authenticated routes

## Acceptance criteria

- Auth state always drives header controls and protected route behavior correctly
- Post-auth redirect lands on dashboard with no intermediate dead-end route
- Shared layout shell is reused by dashboard and editor routes
- Shell styling conforms to p5_pr01 style guide (tokens, spacing, typography)
- Left nav structure is in place for Pipelines, Triggers, Database Targets, Account (per PRD target configuration)

## Out of scope

- Filling out dashboard subpages (Pipelines list, Connections list, Account) — p5_pr03
- Pipeline editor route or graph UI — p5_pr04
- New auth providers or sign-up flows beyond existing Phase 2 baseline

## Dependencies

- p5_pr01 style guide foundations complete (tokens and layout guidance)
- Existing auth/routing baseline in `notion_pipeliner_ui` (Phase 2)

---

## Manual validation steps (after implementation)

1. Sign out; confirm Sign In / Sign Up link visible in upper right.
2. Sign in; confirm redirect to `/dashboard` and Sign Out visible.
3. Navigate to protected route while signed out; confirm redirect to auth or landing.
4. Verify layout shell (left nav + top bar) wraps dashboard and any placeholder editor route.
5. Confirm no duplicate or conflicting layout wrappers.

## Verification checklist

- [ ] Top utility area shows Sign In when signed out, Sign Out when signed in
- [ ] Post-auth redirect goes to /dashboard
- [ ] Shared layout shell wraps authenticated routes
- [ ] Left nav structure present (sections may be placeholder links until p5_pr03)
- [ ] Styling matches p5_pr01 tokens
