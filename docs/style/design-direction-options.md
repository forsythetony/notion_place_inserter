# Notion Pipeliner UI Design Direction Options

Date: 2026-03-14  
Status: **Decided — Option A - Calm Graphite**

## Goals and Constraints

This document proposes visual design directions for `notion_pipeliner_ui` based on product needs:

- Modern, clean, simple visual language.
- Dense enough to support a pipeline editor, but not "tiny" or cramped.
- Dark, modern palette preference, but calm/zen over synthwave/futuristic.
- Consistent system across:
  - Public pages (`Home`, `About`)
  - Authenticated app (`Dashboard`, `Pipelines`, `Database targets`, `Triggers`, `Account`)
- Pipeline editor is the primary interaction surface:
  - stage boxes
  - drag/move interactions
  - connectors/arrows between elements

## Research Inputs

The options below are informed by:

- Linear redesign notes (hierarchy, reduced visual noise, dense-but-readable information).
- Atlassian navigation principles (clear yet unobtrusive navigation; progressive disclosure).
- Material Design 3 accessibility guidance (dark theme contrast and semantic color role discipline).
- Node-based workflow editor UX best practices (zoom/pan, selection clarity, connector ergonomics, minimap/grid behaviors).

### Reference Links

- Linear redesign:
  - https://linear.app/changelog/2024-03-20-new-linear-ui
  - https://linear.app/now/how-we-redesigned-the-linear-ui
  - https://linear.app/now/behind-the-latest-design-refresh
- Atlassian navigation:
  - https://atlassian.design/components/side-navigation/
  - https://www.atlassian.com/blog/design/designing-atlassians-new-navigation
- Material Design 3 color and contrast:
  - https://m3.material.io/foundations/designing/color-contrast
  - https://m3.material.io/styles/color/the-color-system/accessibility
- Workflow editor interaction references:
  - https://latenode.com/blog/best-practices-for-drag-and-drop-workflow-ui
  - https://flow.foblex.com/examples/drag-to-connect

## Shared Foundation (applies to all options)

- **Density target:** medium density (more breathing room than Linear defaults).
- **Base spacing:** 8px scale, with common jumps at 12/16/24/32.
- **Type scale:** minimum body size 14-15px (avoid tiny defaults).
- **Touch targets:** minimum 36px height for primary interactive controls.
- **Contrast:** WCAG-oriented targets:
  - Body/small text >= 4.5:1
  - Large text >= 3:1
  - Key UI boundaries and controls >= 3:1 where applicable
- **Navigation model:** subtle left nav + restrained top utility bar.
- **Pipeline editor defaults:** visible grid, clear selected state, high-legibility connector lines, obvious hover/focus affordances.

---

## Option A - Calm Graphite (Recommended)

Linear-inspired density and hierarchy, but with larger type and softer contrast transitions for a calmer, more "zen" feel.

### Visual Character

- Dark-first, neutral graphite surfaces (not neon).
- Soft layer separation with low-contrast borders and elevation.
- Slightly larger typography than Linear for readability.
- Limited accent usage for actions, status, and selected elements only.

### Example Token Direction (Draft)

- Background: `#111318`
- Surface-1: `#161A22`
- Surface-2: `#1C212B`
- Border: `#2A3140`
- Primary text: `#E8EDF5`
- Secondary text: `#A9B3C3`
- Accent (calm blue): `#7AA2F7`
- Success: `#59C08B`
- Warning: `#D9A35B`
- Danger: `#D66A6A`

### Why It Fits

- Matches the "modern dark" preference.
- Supports high information density without making everything feel tiny.
- Scales well to pipeline editing where focus states and object hierarchy must be instantly clear.

### Risks

- Can still feel "tool-heavy" if spacing is overly compressed.
- Needs disciplined text sizing rules to avoid drifting back into too-small UI.

---

## Option B - Mist Zen (Light-leaning Neutral)

A calm, airy, neutral system with light mode as primary and a carefully mirrored dark mode.

### Visual Character

- Off-white and slate neutrals.
- Strong whitespace and simplified surfaces.
- Highest perceived calmness; lower visual intensity.

### Why It Fits

- Very approachable and clean for less technical users.
- Makes public pages feel polished and editorial.

### Risks

- May under-deliver on your dark-mode preference.
- Pipeline editor can feel less focused unless selection and connector contrast are carefully tuned.

---

## Option C - Monochrome Utility + Single Accent

Near-monochrome interface with one brand accent color used sparingly.

### Visual Character

- High restraint: grayscale UI with one accent channel.
- Extremely clean and minimal visual language.

### Why It Fits

- Strong consistency across public and app experiences.
- Easy long-term maintenance if token discipline is strict.

### Risks

- Can feel sterile if over-minimized.
- Requires excellent interaction microstates (hover/focus/drag) so usability does not suffer.

---

## Pipeline Editor-Specific Implications

Regardless of option, these are required for the editor UX:

- **Node readability:** title + metadata remain legible at normal zoom.
- **Connector clarity:** line thickness, color, and endpoint affordances must be visible on dark surfaces.
- **Selection hierarchy:** selected node/edge states are unmistakable.
- **Canvas orientation:** subtle grid, optional minimap, and stable zoom anchors.
- **Interaction feedback:** drag hover, valid/invalid connect states, and keyboard multi-select states must be explicit.

## Navigation and Layout Recommendation

- Left sidebar for primary sections:
  - `Pipelines`
  - `Triggers`
  - `Database Targets`
  - `Account`
- Top utility area for global actions (search, account, quick create).
- Dashboard and public pages should use the same typography and color tokens, with lighter structural complexity on public pages.

## Recommendation

Choose **Option A - Calm Graphite**.

It best matches your stated taste:

- modern and dark
- clean and simple
- information-dense but not tiny
- practical for a graph/canvas-heavy pipeline editor

## Final Decision

**Option A - Calm Graphite** has been selected.

Next steps: create the full style guide set in `notion_pipeliner_ui/styleguide/`:

- `design-principles.md`
- `layout-and-navigation.md`
- `color-and-theme.md`
- `components.md`
- `pipeline-editor.md`
- `dos-and-donts.md`
