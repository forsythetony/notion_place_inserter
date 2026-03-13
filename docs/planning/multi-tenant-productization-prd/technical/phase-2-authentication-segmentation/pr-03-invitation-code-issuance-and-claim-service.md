# PR 03 - Invitation Code Issuance and Claim Service

## Objective

Implement backend invitation-code issuance and claim lifecycle logic, including single-use enforcement and user-type assignment source of truth.

## Scope

- Add backend service/repository methods to:
  - create invitation code records
  - validate unclaimed invitation codes
  - claim codes atomically
- Ensure claim is single-use and race-safe.
- Persist claim timestamps and claimed flags.
- Expose backend API contract(s) for invite-code validation/claim flow used by sign-up.

## Expected changes

- Service-layer logic for issue/validate/claim.
- Transaction-safe repository operations.
- Endpoint/controller wiring for invite claim flow.
- Error contract for invalid/expired/already-claimed codes.

## Acceptance criteria

- Two concurrent claim attempts cannot both succeed for one code.
- Successful claim transitions record to claimed state with timestamps.
- Claim path returns/propagates invite `user_type` for signup provisioning.
- API returns deterministic errors for invalid and already-claimed codes.

## Out of scope

- Manual operator script for bulk code generation.
- Frontend auth pages and forms.

## Dependencies

- Requires PR 01 and PR 02.

---

## Manual validation steps (after implementation)

1. Create a new invitation code using the issue path and confirm persisted unclaimed state.
2. Validate that the code is recognized as claimable before claim.
3. Claim the code once and verify:
   - `claimed = true`
   - `claimed_at`/`date_claimed` are populated
4. Attempt to claim the same code again and verify deterministic failure.
5. Trigger two near-simultaneous claim attempts for the same code and confirm only one succeeds.
6. Confirm claim response carries invite `user_type` for downstream signup provisioning.

## Verification checklist

- [ ] Issue path creates correctly shaped invite records.
- [ ] Claim path is single-use and race-safe.
- [ ] Claim timestamps/flags persist correctly.
- [ ] Invalid/already-claimed codes return expected errors.
- [ ] `user_type` is propagated from invite claim result.
