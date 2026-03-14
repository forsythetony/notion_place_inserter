# p2_pr03 - Invitation Code Issuance and Claim Service

## Objective

Implement backend invitation-code issuance and claim lifecycle logic, including single-use enforcement and user-type assignment source of truth.

## Scope

- Add backend service/repository methods to:
  - create invitation code records
  - validate unclaimed invitation codes
  - claim codes atomically
- Ensure claim is single-use and race-safe.
- Persist claim timestamps and claimed flags.
- Add issuance endpoint that accepts POST body:
  - `userType`
  - `issuedTo`
  - `platformIssuedOn`
- Gate issuance endpoint to `ADMIN` users only.
- Expose backend API contract(s) for invite-code validation/claim flow used by sign-up, where a valid claim code allows backend account creation.

## Expected changes

- Service-layer logic for issue/validate/claim.
- Transaction-safe repository operations.
- Endpoint/controller wiring for invite issuance + claim flow.
- Error contract for invalid/expired/already-claimed codes.
- Authorization checks and error contract for non-admin issuance attempts.

## Acceptance criteria

- Two concurrent claim attempts cannot both succeed for one code.
- Successful claim transitions record to claimed state with timestamps.
- Claim path returns/propagates invite `user_type` for signup provisioning.
- During sign-up, when a valid unclaimed code is submitted, backend account creation proceeds.
- Issuance endpoint accepts `userType`, `issuedTo`, and `platformIssuedOn` in POST body and persists corresponding invite metadata.
- Non-admin callers cannot issue codes (authorization failure response is deterministic).
- API returns deterministic errors for invalid and already-claimed codes.

## Out of scope

- Frontend auth pages and forms.
- In-site invitation-code issuance UI/path.

## Dependencies

- Requires p2_pr01 and p2_pr02.

---

## Manual validation steps (after implementation)

1. Call issuance endpoint as an `ADMIN` user with `userType`, `issuedTo`, and `platformIssuedOn`; confirm persisted unclaimed invite state and stored metadata.
2. Validate that the code is recognized as claimable before claim.
3. Claim the code once during signup and verify backend account creation proceeds, then verify:
   - `claimed = true`
   - `claimed_at`/`date_claimed` are populated
4. Attempt to claim the same code again and verify deterministic failure.
5. Trigger two near-simultaneous claim attempts for the same code and confirm only one succeeds.
6. Call issuance endpoint as non-admin and verify deterministic authorization failure.
7. Confirm claim response carries invite `user_type` for downstream signup provisioning.

## Verification checklist

- [ ] Issuance endpoint persists correctly shaped invite records from `userType`, `issuedTo`, and `platformIssuedOn`.
- [ ] Claim path is single-use and race-safe.
- [ ] Claim timestamps/flags persist correctly.
- [ ] Invalid/already-claimed codes return expected errors.
- [ ] `user_type` is propagated from invite claim result.
- [ ] Valid signup claim code allows backend account creation.
- [ ] Issuance endpoint rejects non-admin callers.
