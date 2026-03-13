# Phase 2 PR Task Index

This folder breaks Phase 2 authentication and segmentation into PR-sized stories. Complete them in order to avoid coupling frontend auth UX to unfinished backend and data-model foundations.

## Required order

1. [`p2_pr01-auth-schema-user-profile-and-invite-codes.md`](./p2_pr01-auth-schema-user-profile-and-invite-codes.md)
2. [`p2_pr02-backend-auth-context-and-protected-dashboard-contract.md`](./p2_pr02-backend-auth-context-and-protected-dashboard-contract.md)
3. [`p2_pr03-invitation-code-issuance-and-claim-service.md`](./p2_pr03-invitation-code-issuance-and-claim-service.md)
4. [`p2_pr04-manual-invitation-code-generation-script.md`](./p2_pr04-manual-invitation-code-generation-script.md)
5. [`p2_pr05-frontend-landing-auth-and-dashboard-routing.md`](./p2_pr05-frontend-landing-auth-and-dashboard-routing.md)
6. [`p2_pr06-sign-up-with-invite-code-and-user-type-assignment.md`](./p2_pr06-sign-up-with-invite-code-and-user-type-assignment.md)
7. [`p2_pr07-tests-observability-and-phase2-docs.md`](./p2_pr07-tests-observability-and-phase2-docs.md)

## Why this sequence

- p2_pr01 creates the data-model and enum foundation (`user_type`, invitation-code lifecycle fields).
- p2_pr02–p2_pr03 wire backend auth context, route protection, and invite claim semantics.
- p2_pr04 adds operator tooling so invite codes can be generated before broad signup testing.
- p2_pr05–p2_pr06 ship the minimal frontend auth UX and invite-code signup behavior.
- p2_pr07 hardens tests/docs and finalizes operational guidance.

## Completion definition for this phase

Phase 2 is complete when p2_pr01–p2_pr07 are merged and validated together in a shared environment:

- unauthenticated users see public landing and can navigate to sign in/sign up
- authenticated users are redirected to dashboard landing page
- dashboard remains minimal and only exposes `Run Location Inserter (with dummy data)`
- invite codes are generated, claimed once, and assign `user_type` (`ADMIN`, `STANDARD`, `BETA_TESTER`) at signup
- auth and invite flows are covered by tests and documented operationally
