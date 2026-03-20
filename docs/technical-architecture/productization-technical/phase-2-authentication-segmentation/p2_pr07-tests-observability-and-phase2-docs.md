# p2_pr07 - Tests, Observability, and Phase 2 Docs

## Objective

Harden Phase 2 auth/invite functionality with targeted tests, logging, and operational documentation for deployment and manual verification.

## Scope

- Add/expand automated tests for:
  - auth-protected route behavior
  - invitation code issue/claim lifecycle
  - single-use claim guarantees
  - invite-driven `user_type` assignment
  - frontend auth-routing happy and failure paths (as practical)
- Add structured logging around invite issue/claim and auth bootstrap failures.
- Update docs/runbooks for:
  - required environment variables
  - manual test walkthrough for auth/invite flows
  - operator invite generation workflow

## Expected changes

- Backend tests for claim semantics and auth checks.
- Frontend tests (or documented manual checklist where test harness is limited).
- Docs updates across phase folder and relevant READMEs.

## Acceptance criteria

- Critical auth and invite flows are covered by tests or explicit manual checklist.
- Logs are sufficient to diagnose common auth/invite failures.
- Operators can follow docs to generate invite codes and verify signup/dashboard flow.
- Phase 2 documentation is internally consistent and points to canonical run/verify steps.

## Out of scope

- New product features beyond Phase 2 auth/segmentation goals.

## Dependencies

- Requires p2_pr01 through p2_pr06.

---

## Manual validation steps (after implementation)

1. Run backend test suite sections covering auth and invitation claim lifecycle.
2. Run frontend tests for auth routing and signup flows (or execute documented manual checklist if tests are limited).
3. Trigger representative failures (invalid token, already-claimed invite) and inspect logs for actionable context.
4. Validate docs: follow env setup, generate an invite code, complete signup, and reach dashboard.
5. Cross-check API/docs/runbook language for consistency with shipped behavior.

## Verification checklist

- [ ] Critical auth/invite paths are test-covered or explicitly checklist-covered.
- [ ] Logging is sufficient to diagnose auth/invite failures.
- [ ] Operator workflow docs are runnable end-to-end.
- [ ] Phase 2 docs are consistent across PR/story files and runbooks.
