# PR 01 - Phase 2 Auth Schema, User Profile, and Invite Codes

## Objective

Establish the Phase 2 data-model foundation for authentication segmentation: user profile type support and invitation code persistence.

## Scope

- Add `user_type` enum with exactly:
  - `ADMIN`
  - `STANDARD`
  - `BETA_TESTER`
- Add/extend user profile table to store `user_type`.
- Add invitation code table linked to user profile data.
- Model required invite fields:
  - `code` (20-char unique string)
  - `date_issued`
  - `date_claimed` (nullable)
  - `issued_to` (free text)
  - `platform_issued_on` (free text)
  - `claimed` (boolean)
  - `claimed_at` (nullable datetime)
  - `user_type` (enum)
- Add DB constraints/indexes for uniqueness and claim integrity.

## Expected changes

- New SQL migration(s) for enum/table/index/constraints.
- Repository/model updates for profile and invitation-code records.
- Minimal schema documentation updates.

## Acceptance criteria

- Schema migrations apply cleanly on local and shared environments.
- Invitation code uniqueness is enforced at DB level.
- `user_type` validation is enforced by enum constraint.
- Claim metadata fields support unclaimed and claimed states.

## Out of scope

- API endpoints for claim/issue.
- Frontend auth UX.

## Dependencies

- None (first PR in sequence).

---

## Manual validation steps (after implementation)

1. Apply the new migration(s) in a clean local database.
2. Confirm enum values exist and are exactly `ADMIN`, `STANDARD`, `BETA_TESTER`.
3. Insert one unclaimed invitation-code row and verify required fields persist.
4. Attempt to insert a duplicate `code` value and confirm DB uniqueness rejection.
5. Insert/verify a user profile row with each `user_type` value.
6. Roll migration forward on a shared/dev environment and confirm no drift.

## Verification checklist

- [ ] Migration applies cleanly from a fresh checkout.
- [ ] `user_type` enum allows only supported values.
- [ ] Invitation code uniqueness is enforced.
- [ ] Unclaimed and claimed field states are representable.
- [ ] Schema docs reflect final table/enum definitions.
