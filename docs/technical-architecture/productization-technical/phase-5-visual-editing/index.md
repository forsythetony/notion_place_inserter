# Phase 5 Architecture: Visual Editing

## Status

- p5_pr01–p5_pr04 complete (2026-03-16)
- Scope: add rich visual pipeline editor; dual view (visual + structured); style guide foundation; dashboard management surfaces

## Phase 5 PR Task Index

This folder breaks Phase 5 visual editing into PR-sized stories. Complete them in order so navigation, styling, and management surfaces are in place before the pipeline editor.

### Required order

1. [p5_pr01-style-guide-foundation.md](./p5_pr01-style-guide-foundation.md)
2. [p5_pr02-navigation-shell-and-auth-landing.md](./p5_pr02-navigation-shell-and-auth-landing.md)
3. [p5_pr03-dashboard-management-surfaces.md](./p5_pr03-dashboard-management-surfaces.md)
4. [p5_pr04-visual-pipeline-editor-persistence.md](./p5_pr04-visual-pipeline-editor-persistence.md)

### Why this sequence

- p5_pr01 establishes design tokens, component specs, and pipeline-editor visual rules so all subsequent UI work is consistent.
- p5_pr02 delivers the app shell and auth-driven navigation so dashboard and editor routes share a common layout.
- p5_pr03 fills out Pipelines, Connections, and Account management pages so users can browse, create, and open pipelines before editing.
- p5_pr04 builds the React Flow-based editor with API persistence, depending on style guide, shell, and pipelines list.

### Completion definition for this phase

Phase 5 is complete when p5_pr01–p5_pr04 are merged and validated together:

- style guide documents define tokens and component behavior for all Phase 5 surfaces
- authenticated users land on dashboard with consistent nav and sign-in/sign-out
- Pipelines, Connections, and Account pages are functional and wired to backend
- users can create/edit pipelines visually, persist via API, and round-trip definitions reliably

### Manual validation and operator workflow

- **Style guide:** Confirm all six styleguide docs exist and cover tokens, layout, components, pipeline editor, and dos/donts.
- **Navigation:** Sign out, sign in, confirm redirect to dashboard; verify shell is reused by dashboard and editor.
- **Dashboard:** Navigate Pipelines, Connections, Account; create/open pipeline from list.
- **Editor:** Open pipeline, edit graph, save, reload; confirm round-trip fidelity and validation feedback.

---

## Purpose

Phase 5 adds the visual-first pipeline authoring experience described in the PRD. Users configure triggers, data sources, data targets, stages, pipelines, and pipeline steps through the UI. The visual editor stays aligned with the structured text representation so users can move between both views.

### What Phase 4 provides

- Datastore-backed definitions (jobs, stages, pipelines, steps)
- APIs for CRUD and validation
- RLS-enforced tenant isolation
- Snapshot-backed execution

### What Phase 5 adds

- Style guide and design system
- App navigation shell with auth controls
- Dashboard management pages (Pipelines, Connections, Account)
- React Flow-based visual pipeline editor with API persistence

### Architecture anchors

- [PRD Phase 5](../../../feature-proposals/multi-tenant-productization-prd.md#phase-5-visual-editing) · [on GitHub](https://github.com/forsythetony/notion_place_inserter/blob/main/docs/feature-proposals/multi-tenant-productization-prd.md#phase-5-visual-editing)
- [Design direction (Option A - Calm Graphite)](../../../style/design-direction-options.md)
- [Pipeline editor library research (React Flow)](../../../market-research/pipeline-editor-library-research.md)
- [Graph view iconography deep dive](./graph-view-iconography-deep-dive.md)
- [p5 — Admin runtime theme (tech spec)](./p5_admin-runtime-theme-spec.md) — global presets, admin-only CRUD, `/theme/runtime` for CSS variables (draft)
- [p5 — Trigger request body schema](./p5_trigger-request-body-schema-architecture.md) — flat typed POST body per trigger, UI guard rails, graph + inspector preview
- [p5 — Trigger management API (body schema)](./p5_trigger-management-ui-body-schema.md) — `body_fields`, GET/PATCH shape
- [p5 — Trigger UI implementation guide](./p5_trigger-ui-implementation-guide.md) — detailed frontend plan for `notion_pipeliner_ui` (outside this repo); end-user trigger management, not admin-only
- [p5 — Pipeline live testing](./p5_pipeline-live-testing-architecture.md) — run-from-editor architecture, trigger-derived saved test inputs, full-job vs stage-scoped execution
- [p5 — Pipeline step vertical drag reorder (graph editor)](./p5_pipeline-step-drag-reorder-architecture.md) — axis-locked step reorder, neighbor preview, in-memory `sequence`; save-only persistence
- [Phase 4 datastore-backed definitions](../phase-4-datastore-backed-definitions/index.md)
- [Notion onboarding and database selection deep dive](./notion-onboarding-and-database-selection-deep-dive.md)
