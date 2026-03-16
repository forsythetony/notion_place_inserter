# Tech Debt Story: Trigger Secret Plaintext in List Response

## ID

- `td-2026-03-15-trigger-secret-plaintext-in-list-response`

## Status

- Backlog

## Why this exists

As of 2026-03-15, `GET /management/triggers` returns the plaintext `secret` for each trigger in the response payload. The Triggers UI displays these secrets with an eye-toggle to mask/unmask them inline. This improves UX (users can view and copy secrets without a separate reveal flow) but increases the attack surface for secret exposure.

Without a focused security analysis, we risk:
- secrets persisting in browser memory, devtools, or screenshots longer than necessary,
- accidental exposure via support tooling, screen sharing, or logs,
- broader blast radius if a management JWT is compromised (attacker gets all trigger secrets in one call),
- compliance or audit gaps if secret reads are not tracked.

## Goal

Evaluate security implications of returning plaintext trigger secrets in `GET /management/triggers` and document recommended mitigations and alternatives so future hardening can be prioritized explicitly.

## In Scope

- **Security implications**
  - Document how plaintext secrets flow (API → frontend → DOM, clipboard, memory).
  - Assess risk of JWT compromise vs. per-secret reveal (blast radius).
  - Consider browser devtools, screenshots, screen sharing, and support/session-replay tooling.
  - Identify any compliance or audit requirements for secret access.

- **Mitigations and alternatives**
  - **Reveal-on-demand endpoint**: `GET /management/triggers/{id}/secret` that returns the secret only when explicitly requested; list response omits `secret`.
  - **Short-lived reveal tokens**: Backend issues a time-limited token that can be exchanged for the secret; reduces window of exposure.
  - **Audit logging**: Log when secrets are read (list vs. reveal) and by whom; support compliance and incident response.
  - **Masking defaults**: Ensure UI defaults to masked; consider server-side masking (e.g., `secret: null` in list, require explicit reveal).
  - **Operational guidance**: Document best practices for screenshots, support tooling, and session recording when secrets may be visible.

- **Decision criteria**
  - **Risk**: Likelihood and impact of secret exposure (JWT compromise, XSS, physical access, support tooling).
  - **UX impact**: Friction of reveal-on-demand vs. inline visibility; copy affordance and workflow.
  - **Implementation complexity**: Effort to add reveal endpoint, audit logging, or token exchange.
  - **Backward compatibility**: Whether existing clients expect `secret` in list; migration path if we remove it.

## Out of Scope

- Changing the current implementation immediately (this is an analysis story).
- Vault or external secret-backend integration.
- Per-trigger RBAC or fine-grained secret access control (future consideration).

## Suggested Validation Tasks

1. **Threat model**
   - Enumerate assets (trigger secrets), actors (authenticated owner, attacker with stolen JWT, support staff), and trust boundaries.
   - Document attack vectors: JWT theft, XSS, physical access, logs, screenshots, support tooling.

2. **Alternatives comparison**
   - Compare current approach (plaintext in list) vs. reveal-on-demand vs. short-lived tokens.
   - Score each on risk, UX, complexity, and compatibility.

3. **Audit logging**
   - If audit logging is recommended, define events (e.g., `trigger.secret.read`, `trigger.secret.revealed`) and retention.

4. **Operational guidance**
   - Draft internal guidance for support, screenshots, and session recording when secrets may be visible.
   - Consider CSP or other headers to reduce XSS risk.

## Acceptance Criteria

- Security implications are documented with risk assessment.
- At least three mitigation options are evaluated with pros/cons.
- Decision criteria (risk, UX, complexity, compatibility) are captured for prioritization.
- A recommended path (or "accept risk" with rationale) is documented for future hardening.

## Primary Code Areas

- `app/routes/management.py` (GET /management/triggers)
- `notion_pipeliner_ui/src/routes/TriggersPage.tsx` (secret display, eye toggle)
- `notion_pipeliner_ui/src/lib/api.ts` (ManagementTriggerItem.secret)

## Notes

- Current implementation uses owner-scoped auth (`require_managed_auth`, `list_by_owner`); only the authenticated owner can read their triggers and secrets.
- Supabase Bearer auth protects management endpoints; trigger-secret auth remains separate for public invocation.
- This story does not block current UX; it provides a basis for future security hardening decisions.
