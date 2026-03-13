# PR 02 - Backend Auth Context and Protected Dashboard Contract

## Objective

Introduce backend authentication context handling and a minimal protected contract that the dashboard can rely on after login.

## Scope

- Integrate managed auth token/session validation in backend request lifecycle.
- Add authenticated user context extraction for API handlers.
- Add/confirm protected endpoint(s) used by dashboard landing.
- Enforce unauthenticated access rejection behavior (401/403 as applicable).
- Return basic authenticated profile payload including `user_type`.

## Expected changes

- Auth middleware/dependency wiring.
- Profile/repository lookup path for authenticated principal.
- Protected route(s) and response contract for dashboard bootstrapping.
- API docs update for auth-protected routes.

## Acceptance criteria

- Valid authenticated requests receive protected response payload.
- Invalid/missing auth is rejected consistently.
- Response includes stable fields needed by frontend auth-routing logic.
- `user_type` is available in authenticated context.

## Out of scope

- Invitation code issue/claim APIs.
- Landing/auth page frontend implementation.

## Dependencies

- Requires PR 01.

---

## Manual validation steps (after implementation)

1. Start backend with auth configuration enabled.
2. Call a protected endpoint without auth and verify rejection (`401` or expected policy code).
3. Call the same endpoint with an invalid/expired token and verify deterministic rejection.
4. Call with a valid token for a known user and verify success response.
5. Confirm response includes profile fields needed by frontend bootstrap, including `user_type`.
6. Verify dashboard bootstrap endpoint behavior remains stable across repeated calls.

## Verification checklist

- [ ] Missing auth is rejected consistently.
- [ ] Invalid auth is rejected consistently.
- [ ] Valid auth returns protected payload.
- [ ] `user_type` is present in authenticated context/response.
- [ ] API docs match actual auth behavior.
