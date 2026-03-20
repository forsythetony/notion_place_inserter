# Architecture Proposal: Add Step (+) Button Within Pipeline

Date: 2026-03-19  
Status: Proposed  
Owner: Product + Platform

## Problem

The current pipeline UI displays a vertical stack of step cards within each pipeline (e.g., "Research Pipeline"). Users can see the steps but have no obvious, in-context control to add a new step. The "Add Pipeline" button at the section level creates new pipelines, not new steps within an existing pipeline.

To add a step, users must either:
- Use a different entry point (e.g., inspector, context menu, or header action) that may not be discoverable
- Or no clear mechanism exists at all

The pipeline step list has sufficient vertical space below the last step card — there is room for a dedicated "add step" affordance without crowding the layout.

## Goals

- **In-context discovery** — Place an "Add step" (+) button directly below the pipeline's step list so users can add steps without leaving the pipeline view.
- **Consistent placement** — The button lives at the bottom of the step stack, inside the pipeline container, with clear visual hierarchy.
- **Sufficient space** — Reserve enough vertical padding in the pipeline container so the plus button has room to exist without feeling cramped.
- **Aligned behavior** — Clicking the button triggers the same Add Step flow described in [p5_proposal-details-view-cleanup.md](./p5_proposal-details-view-cleanup.md): create a draft step, select it, open inspector in Step setup mode.

## Non-goals

- Changing the Add Step flow or backend step creation logic.
- Adding steps via drag-and-drop or between-step insertion in this proposal.
- Modifying the "Add Pipeline" button or section-level controls.

---

## Current UI Structure (from screenshot)

```
┌─ Research ───────────────────────────────────────────── [Add Pipeline] ─┐
│                                                                         │
│  ┌─ Research Pipeline ──────────────────────────────────────────────┐  │
│  │                                                                   │  │
│  │  ┌─────────────────────────────────────────────────────────────┐ │  │
│  │  │ ● Optimize                              [AI]                 │ │  │
│  │  └─────────────────────────────────────────────────────────────┘ │  │
│  │  ┌─────────────────────────────────────────────────────────────┐ │  │
│  │  │ ● step_google_places_look...                    [G]         │ │  │
│  │  └─────────────────────────────────────────────────────────────┘ │  │
│  │  ┌─────────────────────────────────────────────────────────────┐ │  │
│  │  │ ● step_cache_places                              [DB]       │ │  │
│  │  └─────────────────────────────────────────────────────────────┘ │  │
│  │  ┌─────────────────────────────────────────────────────────────┐ │  │
│  │  │ ● step_cache_place                               [DB]       │ │  │
│  │  └─────────────────────────────────────────────────────────────┘ │  │
│  │                                                                   │  │
│  │  ┌─────────────────────────────────────────────────────────────┐ │  │
│  │  │                        [ + ]  ← Add step button              │ │  │
│  │  └─────────────────────────────────────────────────────────────┘ │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Proposed Design

### Placement

- **Location:** Directly below the last step card, inside the pipeline container (e.g., "Research Pipeline").
- **Vertical spacing:** 
  - Minimum 16–24px gap between the last step card and the plus button.
  - The button itself should have a comfortable tap/click target (min 40px height, 44px for touch).
  - Optional: Add a subtle separator (e.g., light divider or extra padding) to distinguish the "add" zone from the step list.

### Button Appearance

| Aspect | Recommendation |
|--------|----------------|
| **Icon** | Plus (+) icon, centered |
| **Style** | Outlined/dashed border to suggest "add" without competing with step cards. Match the pipeline container's border color (e.g., light blue) for consistency. |
| **Label** | Optional: "Add step" text below or beside the icon for clarity. If space is tight, icon-only with `title`/`aria-label` for accessibility. |
| **Hover/focus** | Slight background fill or border emphasis to indicate interactivity. |

### Layout: Full-width pill/bar (chosen)

**Chosen design:** A full-width horizontal bar spanning the pipeline width, with the plus icon centered.

- Clear "this is where you add" affordance.
- Fits the existing card-stack aesthetic.
- Provides a clear, scannable target and reserves consistent space.

---

## Interaction Flow

1. **Click:** User clicks the Add step (+) button.
2. **Create draft:** A new draft step is appended to the pipeline (local editor state). Sequence is set to `last_sequence + 1` (or next available).
3. **Select & inspect:** The new step becomes the selected node. The inspector opens in Step setup mode with the template picker (or command-palette picker per [p5_step-template-picker-architecture.md](./p5_step-template-picker-architecture.md)).
4. **Configure:** User selects a step template and configures the step as in the existing Add Step flow.
5. **Save:** User saves the pipeline; the new step is persisted.

**Keyboard:** When the button has focus, `Enter` or `Space` triggers the same action as click.

---

## Space Requirements

To ensure the plus button has room:

| Element | Min height | Notes |
|---------|------------|-------|
| Gap above button | 16–24px | Between last step and button |
| Button / bar | 40–48px | Comfortable tap target |
| Gap below button | 8–16px | Before pipeline container bottom border |

**Total reserved:** ~64–88px of vertical space for the add-step zone.

The pipeline container should use `min-height` or padding so that even with zero steps, the add-step button is visible and usable (avoid "empty pipeline" collapsing to nothing).

---

## Edge Cases

| Case | Behavior |
|------|----------|
| **Empty pipeline** | Plus button still visible; clicking adds the first step. |
| **At max steps** | Button disabled or hidden; show tooltip/message: "Maximum steps reached" (per `max_steps_per_pipeline` limit). |
| **Read-only / view mode** | Button hidden when pipeline is not editable. |
| **Loading pipeline** | Button disabled or hidden until pipeline data is loaded. |

---

## Data Model & API

No changes to the data model or API. The Add Step flow uses existing:

- `StepInstance` creation (draft or persisted)
- `sequence` assignment
- `GET /management/step-templates` for template picker
- Pipeline save/update endpoints

---

## Implementation Considerations

### Component Structure

- The add-step button should be a sibling to the step list within the pipeline container, not a child of the last step.
- Use a dedicated component (e.g., `PipelineAddStepButton` or `AddStepBar`) for reuse and testing.

### Accessibility

- `role="button"` and `aria-label="Add step"` (or "Add pipeline step").
- Keyboard focusable; visible focus ring.
- Screen reader: "Add step, button" when focused.

### Responsive

- On narrow viewports, the full-width bar can shrink; maintain minimum tap target (44px).
- Consider stacking "Add step" text below the icon if horizontal space is limited.

---

## Relationship to Other Docs

- **[p5_proposal-details-view-cleanup.md](./p5_proposal-details-view-cleanup.md)** — Defines the Add Step flow (draft step, inspector, template picker). This proposal adds the **entry point** (the plus button) within the pipeline view.
- **[p5_step-template-picker-architecture.md](./p5_step-template-picker-architecture.md)** — After the plus button creates a draft step, the template picker (command-palette or dropdown) is used to select the step type.
- **[p5_proposal-trigger-target-aware-pipeline-creation.md](./p5_proposal-trigger-target-aware-pipeline-creation.md)** — "Add Pipeline" remains a section-level action; this proposal is about adding steps **within** an existing pipeline.

---

## Implementation Phases

### Phase 1: Button placement and wiring
- Add the Add step (+) bar/button below the step list in the pipeline container.
- Reserve vertical space per the layout spec.
- Wire click to create draft step, select it, and open inspector in Step setup mode.
- **Effort:** Low–Medium. **Outcome:** Discoverable in-context add-step control.

### Phase 2: Edge cases and polish
- Handle empty pipeline, max steps, read-only mode.
- Accessibility: ARIA, keyboard, focus management.
- Optional label ("Add step") and responsive tweaks.
- **Effort:** Low. **Outcome:** Production-ready behavior.

---

## Acceptance Criteria

- [ ] An "Add step" (+) button appears below the pipeline's step list, inside the pipeline container.
- [ ] There is at least 16px vertical gap between the last step and the button.
- [ ] The button has a minimum 40px height (44px for touch targets).
- [ ] Clicking the button creates a new draft step, selects it, and opens the inspector in Step setup mode.
- [ ] The button is keyboard accessible (focusable, Enter/Space activates).
- [ ] The button has `aria-label="Add step"` (or equivalent).
- [ ] When the pipeline is at `max_steps_per_pipeline`, the button is disabled or hidden with appropriate feedback.
- [ ] When the pipeline is empty, the button is still visible and adds the first step when clicked.
- [ ] In read-only or view mode, the button is hidden.

---

## Resolved Decisions

| Decision | Choice |
|----------|--------|
| Placement | Below last step, inside pipeline container |
| Layout | Full-width pill/bar with centered plus icon |
| Minimum gap | 16–24px above button |
| Edge case: empty pipeline | Button visible; adds first step |
| Edge case: max steps | Button disabled or hidden |
