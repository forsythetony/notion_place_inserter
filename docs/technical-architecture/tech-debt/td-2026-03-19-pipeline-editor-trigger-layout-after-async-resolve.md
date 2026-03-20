# Tech Debt: Pipeline editor graph spacing after trigger metadata loads

## ID

- `td-2026-03-19-pipeline-editor-trigger-layout-after-async-resolve`

## Status

- Backlog

## Where

- **UI repo:** `notion_pipeliner_ui`
- **Primary files:** `src/routes/PipelineEditorPlaceholder.tsx` (graph sync from payload + `graphTriggerDisplay`), `src/lib/graphTransform.ts` (`graphToFlow`, `computeTriggerNodeHeight`)

## Why this exists

The trigger node on the pipeline canvas loads display name, path, and body-schema rows after `GET /management/triggers`. The graph layout (`graphToFlow`) depends on that data and on a computed node height that should match the rendered card.

Despite rebuilding nodes when `graphTriggerDisplay` updates (including a `useLayoutEffect` pass intended to avoid a paint where the stage sits at the “pending” trigger height), **observers still see incorrect vertical spacing** between the trigger and the first stage after the real schema appears—while spacing can look correct briefly with placeholder content.

Likely contributing factors (not fully validated):

- Measured vs. specified node dimensions in React Flow (`style.height` vs. content reflow, fonts, wrapping).
- Remaining one-frame or post-paint layout drift.
- `computeTriggerNodeHeight` drifting from actual CSS (padding, borders, list rows, long titles).

## Goal

Restore **consistent inter-node vertical spacing** (`NODE_VERTICAL_GAP`) after the trigger card has its final content, with no visible “pop” or overlap with the first stage.

## Suggested follow-ups

1. Reproduce with screen recording + React DevTools profiles (network + commit order).
2. Compare `getBoundingClientRect()` height of the trigger wrapper to `computeTriggerNodeHeight` for real triggers.
3. If DOM is taller than the model, either tighten the height formula or drive layout from **measured** heights (re-run `graphToFlow` or shift downstream nodes when trigger `ResizeObserver` fires).
4. Optional: one-shot relayout on `document.fonts.ready` if webfont reflow is involved.

## Out of scope for this note

- Changing product behavior of trigger binding or management APIs.
