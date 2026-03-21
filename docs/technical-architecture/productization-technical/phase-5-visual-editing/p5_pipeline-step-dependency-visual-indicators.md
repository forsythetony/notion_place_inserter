# Pipeline editor: visual indicators for step-to-step flow

Date: 2026-03-20  
Status: Draft (design + implementation guide)  
Primary surface: `notion_pipeliner_ui` pipeline canvas (React Flow)

**Placement:** This file lives under **technical architecture / phase 5** because it ties **graph rendering** (React Flow nodes, edges, layout) to a concrete **UX affordance**. It is not a marketing doc; it is narrower than a full PRD but more engineering-facing than high-level style direction in `docs/style/`.

---

## Problem

Readers of the pipeline canvas should immediately see **how work flows**: each step runs **after** the previous one in the same inner pipeline, and outputs conceptually **feed forward** unless the model says otherwise.

Today, vertical stacking implies order, but **order alone is easy to misread**—especially with nested stage/pipeline chrome, zoom, and distraction from inspector panels. A **lightweight connector** (line or path) between steps reinforces “this step depends on the prior one in this branch” without requiring the user to infer sequence from layout alone.

---

## Goals

1. **Primary read:** Between consecutive steps inside the same inner `PipelineDefinition`, show a **clear visual link** (connector) from the bottom of step *N* to the top of step *N+1*.
2. **Consistent metaphor:** The same visual language should apply wherever the product means **sequential execution along one branch** (not arbitrary graph edges drawn by the user).
3. **Subtle by default:** Connectors should read as **structure**, not as noisy decoration—calm stroke weight, theme-aligned color, optional very light motion where it helps orientation (see below).
4. **Accessible:** Do not rely on color alone; stroke and path shape should remain visible against the canvas background in light and dark themes.

## Non-goals (this doc)

- **Data-binding graph:** Drawing lines for every `input_binding` from an arbitrary upstream step (a full “signal wiring” view). That is a larger feature; sequential connectors are the baseline.
- **Editing edges by dragging:** Users reorder steps via existing step chrome, not by reconnecting graph edges.
- **Parallel branches inside one pipeline:** If the execution model later allows true DAGs within a single inner pipeline, connector semantics must be revisited; v1 assumes **linear `sequence` within a pipeline**.

---

## Terminology

| Term | Meaning here |
|------|----------------|
| **Execution order** | Steps run in `sequence` order within one inner pipeline, as persisted in the job graph. |
| **Sequential connector** | A visual edge meaning “runs after / flows from the previous step on this branch”—not necessarily “every input binding resolves from the step above.” |
| **Data dependency** | A step’s bindings reference outputs or cache keys produced earlier; the analyzer / live-test docs cover that. Sequential connectors **hint** at forward flow; binding UI remains the source of truth for *what* depends on *what*. |

If we ever show **both** sequential flow and **explicit binding** edges, they must use **distinct styles** (e.g. solid neutral stroke vs. accent dashed “signal” edge) so the canvas does not collapse into one undifferentiated mesh.

---

## Current implementation anchor

The editor already builds **step-to-step React Flow edges** when transforming the management payload to the canvas:

- **Trigger → first stage** (when a trigger is present): single edge `e_trigger_stage`.
- **Step *i* → step *i+1*** inside each pipeline: ids `e_<prevStepId>_<step.id>`, `type: "smoothstep"`, `animated: true`.
- **Last step(s) per stage → target** boundary node: one edge per terminal step in parallel pipelines.

Source: `notion_pipeliner_ui/src/lib/graphTransform.ts` (`graphToFlow`).

The React Flow instance in `PipelineEditorPlaceholder.tsx` does not currently centralize `defaultEdgeOptions` / custom edge types; styling largely follows **library defaults**, which may be **too faint** or **too busy** (animated) depending on theme and zoom. This doc is the place to lock **intended** stroke, animation, and z-order behavior and then align CSS / `defaultEdgeOptions` / a small custom edge component with that spec.

---

## Recommended visual language

### Sequential connector (default)

- **Shape:** Vertical-ish smooth step or slight Bézier from **bottom center** of the upstream step node to **top center** of the downstream step (matches current `smoothstep` intent).
- **Stroke:** 1.5–2px **muted neutral** in the admin theme (e.g. token for “border strong” / “graph edge”), **not** the primary accent unless we later introduce a second edge family for “signal” links.
- **Endpoints:** Optional **small dot** or **short perpendicular cap** at each end so the line does not “float” between rectangles; keep caps minimal to avoid icon clutter.
- **Animation:** Prefer **static** stroke for production calmness, or a **very slow, low-contrast** dash offset if motion is kept—avoid prominent “marching ants” for baseline structure. (Today’s `animated: true` on all step edges is a good candidate to revisit against this spec.)

### Trigger → stage and step → target

- Use the **same stroke token** as sequential connectors so the canvas reads as one continuous **job graph**.
- If the target node is a “sink,” a **slightly stronger weight** (e.g. +0.5px) can help termination read clearly without a different hue.

### Zoom and hit area

- Edges are **not** primary interactive targets; keep pointer events consistent with “select step, not edge.”
- At low zoom, stroke should **remain visible** (minimum contrast ratio against `Background` grid).

---

## Theming and implementation notes

1. **Centralize edge appearance** via React Flow `defaultEdgeOptions` (e.g. `style`, `className`) and/or a **single custom edge type** shared by trigger, step, and target links.
2. **Map to admin tokens** when the runtime theme system (`p5_admin-runtime-theme-spec.md`) exposes semantic variables—avoid hard-coded hex in TS unless bridged from CSS variables.
3. **Z-order:** Draw connectors **behind** step nodes but **above** the background grid so they never obscure labels.
4. **Round-trip:** `flowToGraph` intentionally ignores edge list for persistence (`_edges`); layout is **derived from payload**, not from user-drawn edges. Any visual change must **not** require serializing edges to the backend.

---

## Acceptance checklist (when implementing or refreshing the canvas)

- [ ] Consecutive steps in one inner pipeline show a visible connector in **light and dark** admin themes.
- [ ] Trigger→first stage and terminal→target links match the **same family** of styling as step-to-step links.
- [ ] Motion (if any) is **optional or minimal** and does not compete with run-state animations (future).
- [ ] Sequential connectors remain **semantically correct** when steps are reordered (edges regenerated from `graphToFlow`, not hand-edited).
- [ ] Docs / inspector copy do not claim connectors prove **binding-level** dependency without a future binding-overlay feature.

---

## Related docs

- Pipeline live testing and scope semantics: `p5_pipeline-live-testing-architecture.md`
- Admin theme tokens (stroke colors): `p5_admin-runtime-theme-spec.md`
- Graph layout and edge construction: `notion_pipeliner_ui/src/lib/graphTransform.ts`
