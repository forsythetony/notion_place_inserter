# p2_pr04 - Manual Invitation Code Generation Script

## Objective

Provide an operator-friendly manual script/CLI to generate invitation codes for controlled onboarding (especially beta testers).

## Scope

- Add a script/CLI command to create invitation codes manually.
- Support operator-provided metadata:
  - `issued_to`
  - `platform_issued_on`
  - `user_type`
- Generate unique random codes of exactly 20 characters.
- Persist generated codes via backend `POST /auth/invitations` API.
- Document run instructions and examples.

## Expected changes

- New script/CLI entrypoint for invite-code generation (CSV-based workflow).
- Script reads CSV rows (`userType`, `platformIssuedOn`, `issueTo`) and issues via backend API.
- Operator docs in README or phase-specific runbook section.

## Acceptance criteria

- Operator can run one command to create invitation codes from a CSV file.
- Generated codes are always 20 characters and unique.
- Script output clearly reports created codes and metadata.
- Invalid user type input is rejected with clear error output.
- Idempotent: non-empty `issuedTo` returns existing row when already issued.

## Out of scope

- Frontend admin UI for invitation code management.
- Claim-time frontend behavior.

## Dependencies

- Requires p2_pr01 and p2_pr03.

---

## Manual validation steps (after implementation)

1. Run the script for a CSV with one or more rows (`userType`, `platformIssuedOn`, `issueTo`).
2. Verify output includes generated code and selected metadata.
3. Confirm the created record exists in DB with a 20-character code.
4. Run with multiple rows and verify all codes are unique.
5. Run with invalid `user_type` input and confirm command fails with clear error text.
6. Re-run with duplicate `issueTo` and confirm idempotent behavior (returns existing code).

## Verification checklist

- [ ] CSV-based issuance works end-to-end.
- [ ] Multiple rows produce unique 20-character codes.
- [ ] Metadata fields persist correctly.
- [ ] Invalid input is rejected with actionable errors.
- [ ] Operator docs include copy-pastable usage examples.
