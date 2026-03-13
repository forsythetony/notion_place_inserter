# PR 04 - Manual Invitation Code Generation Script

## Objective

Provide an operator-friendly manual script/CLI to generate invitation codes for controlled onboarding (especially beta testers).

## Scope

- Add a script/CLI command to create invitation codes manually.
- Support operator-provided metadata:
  - `issued_to`
  - `platform_issued_on`
  - `user_type`
  - count (single or batch)
- Generate unique random codes of exactly 20 characters.
- Persist generated codes via backend data layer.
- Document run instructions and examples.

## Expected changes

- New script/CLI entrypoint for invite-code generation.
- Shared code-generation helper (deterministic length and character set).
- Operator docs in README or phase-specific runbook section.

## Acceptance criteria

- Operator can run one command to create one or many invitation codes.
- Generated codes are always 20 characters and unique.
- Script output clearly reports created codes and metadata.
- Invalid user type input is rejected with clear error output.

## Out of scope

- Frontend admin UI for invitation code management.
- Claim-time frontend behavior.

## Dependencies

- Requires PR 01 and PR 03.

---

## Manual validation steps (after implementation)

1. Run the script for a single code with explicit `issued_to`, `platform_issued_on`, and `user_type`.
2. Verify output includes generated code and selected metadata.
3. Confirm the created record exists in DB with a 20-character code.
4. Run batch generation (count > 1) and verify all codes are unique.
5. Run with invalid `user_type` input and confirm command fails with clear error text.
6. Re-run with valid inputs and confirm script is idempotent in behavior (no crashes, consistent output format).

## Verification checklist

- [ ] Single-code generation works end-to-end.
- [ ] Batch generation works and produces unique 20-character codes.
- [ ] Metadata fields persist correctly.
- [ ] Invalid input is rejected with actionable errors.
- [ ] Operator docs include copy-pastable usage examples.
