# Tech Debt: EULA accept step broken — signup blocked

## ID

- `td-2026-03-23-eula-accept-page-signup-blocker`

## Status

- Open

## Severity

- **Blocker** — New users cannot complete signup.

## Where

- **UI:** `notion_pipeliner_ui` — signup / auth landing, EULA modal or inline step (`src/routes/AuthPage.tsx`); styles `eula-signup-*` in `App.css`.
- **Client:** `getCurrentEula`, signup helpers in `src/lib/api.ts`.
- **API (if payload/response wrong):** `app/routes/eula.py` — `GET /auth/eula/current`; `SignupOrchestrationService` / `POST /auth/signup` for EULA fields.
- **Design reference:** [eula-versioning-and-acceptance.md](../productization-technical/beta-launch-readiness/eula-versioning-and-acceptance.md)

## Observed behavior

- Users **cannot read** the EULA (text not visible, not scrollable, or otherwise unusable).
- The **accept / continue control does not work** (stays disabled, no-op on click, or errors).
- Together this **blocks signup** for anyone who must pass the EULA gate.

## Steps to reproduce

1. Open the app auth/signup flow with a valid invitation code (environment per team practice).
2. Proceed until the **EULA acceptance** step opens.
3. Attempt to read the full text (scroll if applicable) and click the control to accept and continue.

## Expected behavior

- Published EULA full text is readable (including scroll container if long).
- User can attest (checkbox or equivalent) and submit; client sends `eulaVersionId` matching `GET /auth/eula/current` with signup attestation per API contract.
- Signup completes or surfaces a clear validation/API error—not a dead-end UI.

## Why this exists / notes

- **Root cause:** TBD during fix (CSS/layout, modal focus trap, scroll sentinel logic, disabled gating, failed `getCurrentEula`, or mismatched version id).
- **Proven vs inferred:** Reported as live blocking behavior; exact browser/OS and network tab details to capture during investigation.

## Goal

- Any invited user can read the current EULA and complete acceptance so `POST /auth/signup` succeeds when other inputs are valid.

## Suggested follow-ups

1. Reproduce locally and in staging; fix UI/state/API mismatch.
2. Add or extend `AuthPage` tests for scroll-to-enable and successful signup payload.
3. Short manual QA checklist for signup before releases touching auth/EULA.

## Out of scope for this note

- Changing legal meaning of the EULA or removing the requirement—only fixing broken UX/contract behavior.
