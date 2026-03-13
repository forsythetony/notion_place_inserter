# p2_pr06 - Sign Up with Invite Code and User Type Assignment

## Objective

Connect signup UX to invitation-code claim flow so invited users are provisioned with the correct `user_type`.

## Scope

- Extend sign-up flow to accept invitation code input.
- Validate invitation code before or during account creation.
- Claim code on successful sign-up.
- Ensure created user profile receives `user_type` from claimed code.
- Provide clear user-facing errors for:
  - invalid code
  - already-claimed code
  - claim race/conflict

## Expected changes

- Frontend sign-up form updates for invitation code.
- Backend claim endpoint integration in signup orchestration.
- Auth/profile provisioning path that applies invite `user_type`.
- UX messaging for claim failure modes.

## Acceptance criteria

- Valid invite code signup creates user and assigns expected `user_type`.
- Reusing same code fails and does not create a second claim.
- Claim and user creation are consistent (no partially created broken state).
- User lands on dashboard after successful invite-based signup.

## Out of scope

- Full role-based feature matrix.
- Bulk invite management UI.

## Dependencies

- Requires p2_pr03, p2_pr04, and p2_pr05.

---

## Manual validation steps (after implementation)

1. Generate a fresh invitation code for each `user_type` (`ADMIN`, `STANDARD`, `BETA_TESTER`).
2. Use one valid code in sign-up flow and verify user creation succeeds.
3. Confirm created user profile has `user_type` matching the claimed invitation code.
4. Attempt sign-up with an invalid code and verify user-friendly error.
5. Attempt sign-up with an already-claimed code and verify deterministic failure.
6. Confirm successful invite-based signup ends on dashboard landing page.

## Verification checklist

- [ ] Valid code signup succeeds and claims code once.
- [ ] Assigned `user_type` matches invite `user_type`.
- [ ] Invalid/already-claimed code paths fail gracefully.
- [ ] No partial signup state is left on claim failure.
- [ ] Success flow redirects to dashboard.
