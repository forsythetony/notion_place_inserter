# PR 05 - Frontend Landing, Auth, and Dashboard Routing

## Objective

Ship the minimal Phase 2 frontend route structure: public landing page, auth page, protected dashboard route, and post-auth redirect behavior.

## Scope

- Add public landing page with top-right `Sign In / Sign Up` action.
- Add basic auth page for sign-in/sign-up forms.
- Add protected dashboard landing page route.
- Add route guards and redirect logic:
  - unauthenticated users cannot access dashboard
  - authenticated users are routed to dashboard
- Keep dashboard intentionally minimal with only:
  - `Run Location Inserter (with dummy data)`

## Expected changes

- Frontend routes/components for landing, auth, dashboard.
- Session/auth-state wiring for guards and redirects.
- Minimal UX state handling for loading/auth resolution.

## Acceptance criteria

- Unauthenticated visitors land on public landing page.
- `Sign In / Sign Up` path is reachable and functional.
- Successful authentication sends user to dashboard landing.
- Dashboard route is protected and not publicly accessible.
- No broader pipeline-management UI is introduced.

## Out of scope

- Invite-code claim UX details in sign-up form.
- Admin management UI.

## Dependencies

- Requires PR 02.

---

## Manual validation steps (after implementation)

1. Open the app while signed out and verify the public landing page renders.
2. Confirm top-right `Sign In / Sign Up` action is visible and routes to auth page.
3. Attempt direct navigation to dashboard while signed out and verify redirect/block behavior.
4. Sign in with a valid account and verify automatic navigation to dashboard landing.
5. Refresh on dashboard and confirm session-based access still works.
6. Confirm dashboard only exposes `Run Location Inserter (with dummy data)` and no additional management surfaces.

## Verification checklist

- [ ] Public landing route works for unauthenticated users.
- [ ] Auth route is reachable from top-right action.
- [ ] Protected dashboard route blocks unauthenticated access.
- [ ] Successful auth redirects to dashboard.
- [ ] Dashboard remains intentionally minimal.
