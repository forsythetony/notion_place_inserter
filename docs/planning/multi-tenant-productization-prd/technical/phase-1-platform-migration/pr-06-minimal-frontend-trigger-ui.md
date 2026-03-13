# PR 06 - Minimal Frontend Trigger UI

## Objective

Ship the Phase 1 frontend baseline: a minimal page with one button that triggers the migrated backend endpoint.

## Scope

- Create frontend surface (or minimal app route/page if frontend already exists).
- **Hosting:** Deploy UI to Render Static Site; API remains on Render Web Service.
- Add one action button: `Run Location Inserter`.
- Submit a dummy/test keywords payload to backend endpoint.
- Show simple UI states: idle, submitting, accepted, error.
- Environment wiring: `BASE_URL` for API endpoint; CORS configured so static UI can call API.

## Expected changes

- New frontend app files and minimal styling.
- Environment wiring for backend base URL.
- Basic request handling and status rendering.
- Render Static Site deployment config.

## Acceptance criteria

- Clicking button triggers backend call and receives accepted response in healthy path.
- Error states are visible and non-silent.
- No auth UX introduced in this phase.
- UI deployed to Render Static Site; API calls succeed from static origin.

## Out of scope

- Pipeline management UI, account setup UI, activity history UI.

## Dependencies

- Requires PR 05.
