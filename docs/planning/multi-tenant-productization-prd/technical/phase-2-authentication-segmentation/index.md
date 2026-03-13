# Phase 2 PR Task Index

This folder breaks Phase 2 authentication and segmentation into PR-sized stories. Complete them in order to avoid coupling frontend auth UX to unfinished backend and data-model foundations.

## Required order

1. [`pr-01-phase2-auth-schema-user-profile-and-invite-codes.md`](./pr-01-phase2-auth-schema-user-profile-and-invite-codes.md)
2. [`pr-02-backend-auth-context-and-protected-dashboard-contract.md`](./pr-02-backend-auth-context-and-protected-dashboard-contract.md)
3. [`pr-03-invitation-code-issuance-and-claim-service.md`](./pr-03-invitation-code-issuance-and-claim-service.md)
4. [`pr-04-manual-invitation-code-generation-script.md`](./pr-04-manual-invitation-code-generation-script.md)
5. [`pr-05-frontend-landing-auth-and-dashboard-routing.md`](./pr-05-frontend-landing-auth-and-dashboard-routing.md)
6. [`pr-06-sign-up-with-invite-code-and-user-type-assignment.md`](./pr-06-sign-up-with-invite-code-and-user-type-assignment.md)
7. [`pr-07-tests-observability-and-phase2-docs.md`](./pr-07-tests-observability-and-phase2-docs.md)

## Why this sequence

- PR 1 creates the data-model and enum foundation (`user_type`, invitation-code lifecycle fields).
- PRs 2-3 wire backend auth context, route protection, and invite claim semantics.
- PR 4 adds operator tooling so invite codes can be generated before broad signup testing.
- PRs 5-6 ship the minimal frontend auth UX and invite-code signup behavior.
- PR 7 hardens tests/docs and finalizes operational guidance.

## Completion definition for this phase

Phase 2 is complete when PRs 1-7 are merged and validated together in a shared environment:

- unauthenticated users see public landing and can navigate to sign in/sign up
- authenticated users are redirected to dashboard landing page
- dashboard remains minimal and only exposes `Run Location Inserter (with dummy data)`
- invite codes are generated, claimed once, and assign `user_type` (`ADMIN`, `STANDARD`, `BETA_TESTER`) at signup
- auth and invite flows are covered by tests and documented operationally
