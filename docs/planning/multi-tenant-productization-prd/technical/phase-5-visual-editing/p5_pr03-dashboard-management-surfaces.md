# p5_pr03 - Dashboard Management Surfaces (Pipelines, Connections, Account)

## Objective

Fill out the dashboard area with the core management pages that prepare users for editing and operations: Pipelines list, Connections list, and Account Management page. Wire read/list interactions to existing Phase 4 backend endpoints for user-scoped resources.

## Scope

- Build dashboard subpages for:
  - **Pipelines** list — browse, create new, open existing; handoff to editor route
  - **Connections** list — view and manage integration connections (connector instances)
  - **Account Management** page — account setup, billing placeholder, or equivalent
- Add table/list empty states, loading states, error states, and primary actions (create, open, refresh where relevant)
- Wire read/list interactions to Phase 4 datastore-backed APIs for user-scoped resources
- Apply p5_pr01 style guide for all surfaces

## Expected changes

- Pipelines list page with list/table of job definitions; Create New and Open actions
- Connections list page with list of connector instances; refresh/revalidate where applicable
- Account Management page (functional enough for Phase 5 editor onboarding, not placeholder-only)
- API client calls to backend for jobs, connector instances, and account-related data
- Empty states, loading spinners, and error handling per style guide
- Navigation from Pipelines list to editor route (e.g. `/pipelines/:id` or `/pipelines/new`)

## Acceptance criteria

- Authenticated user can navigate between all three management surfaces via the shared nav (p5_pr02 shell)
- Pipelines list supports "create new" and "open existing" handoff into editor route
- Connections and account pages are functional enough for Phase 5 editor onboarding (not placeholder-only)
- List pages show real data from backend when available; empty and error states render correctly
- Styling conforms to p5_pr01 style guide

## Out of scope

- Pipeline editor implementation — p5_pr04
- Full CRUD for connections (create/edit/delete) beyond list and basic actions
- Billing or payment integration
- Activity history / run history (separate future story)

## Dependencies

- p5_pr02 navigation shell complete
- Phase 4 datastore-backed APIs available for list/detail retrieval (jobs, connector instances, etc.)

---

## Manual validation steps (after implementation)

1. Sign in and navigate to Pipelines; confirm list loads (or empty state).
2. Click "Create New" pipeline; confirm navigation to editor route.
3. Click "Open" on existing pipeline; confirm navigation to editor with id.
4. Navigate to Connections; confirm list loads or empty state.
5. Navigate to Account; confirm page renders with useful content.
6. Verify loading and error states when API fails or returns empty.

## Verification checklist

- [x] Pipelines list page functional with create/open handoff
- [x] Connections list page functional
- [x] Account page functional (not placeholder-only)
- [x] All pages use shared nav from p5_pr02
- [x] API integration for list data
- [x] Empty, loading, error states implemented
- [x] Styling matches p5_pr01

## Implementation note

Route and nav label were renamed from "Database Targets" (`/database-targets`) to "Connections" (`/connections`) per p5_pr03 scope.
