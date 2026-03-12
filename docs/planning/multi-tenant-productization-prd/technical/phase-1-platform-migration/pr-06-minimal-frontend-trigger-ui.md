# PR 06 - Minimal Frontend Trigger UI

## Objective

Ship the Phase 1 frontend baseline: a minimal page with one button that triggers the migrated backend endpoint.

## Scope

- Create frontend surface (or minimal app route/page if frontend already exists).
- Add one action button: `Run Location Inserter`.
- Submit a dummy/test keywords payload to backend endpoint.
- Show simple UI states: idle, submitting, accepted, error.

## Expected changes

- New frontend app files and minimal styling.
- Environment wiring for backend base URL.
- Basic request handling and status rendering.

## Acceptance criteria

- Clicking button triggers backend call and receives accepted response in healthy path.
- Error states are visible and non-silent.
- No auth UX introduced in this phase.

## Out of scope

- Pipeline management UI, account setup UI, activity history UI.

## Dependencies

- Requires PR 05.
