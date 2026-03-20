# Architecture: Step Detail View — Section Visual Hierarchy and Content Priority

Date: 2026-03-19  
Status: Proposed  
Owner: Product + Platform

## Problem

The Step detail view (inspector) is visually crowded and difficult to scan. Two related issues:

1. **Flat hierarchy** — All sections and fields appear at the same visual weight. Users cannot quickly find what matters most when configuring a step.
2. **Wrong emphasis** — The layout treats step metadata (display name, sequence, failure policy) as equal in importance to the core configuration. In practice, users care most about:
   - **What does this step do?** → Step-specific configuration (e.g., which property to set, which values to constrain)
   - **Where does the data come from?** → Input value / bindings
   - **What does this step produce?** → Expected output value / preview

Sequence and failure policy matter, but they are secondary—users rarely change them. They should not compete for attention with Configuration, Inputs, and Output.

---

## Goals

- **Prioritize the primary workflow** — Configuration, Inputs, and Output are the most important sections. They should be visually prominent and easy to find.
- **Deprioritize step metadata** — Display name, sequence, and failure policy should be compact, collapsible, or visually secondary so they do not distract from the main configuration flow.
- **Create clear section boundaries** — Users should immediately distinguish Configuration from Inputs from Output.
- **Improve label–field grouping** — Each field should be visually associated with its label; spacing should reinforce hierarchy.
- Preserve dark mode compatibility and alignment with existing design system (see [p5_pr01-style-guide-foundation.md](./p5_pr01-style-guide-foundation.md)).

## Non-goals

- Changing the underlying schema or data model.
- Removing sequence, failure policy, or display name—they remain available, just de-emphasized.
- Replacing the underlying form controls or layout engine.

---

## Content Priority Model

### Primary (Most Important)

| Section | Why it matters |
|---------|----------------|
| **INPUTS** | Defines *where the data comes from*—the upstream signal or value. Users need to wire steps together; input bindings are critical. |
| **CONFIGURATION** | Defines *what the step does*—e.g., which property to set, which values to allow, which icon to use. This is the heart of step configuration. |
| **OUTPUT** | Defines *what the step produces*—the expected output shape and value. Helps users understand the pipeline flow and verify correctness. |

### Secondary (Important but Less Frequently Changed)

| Section | Why it matters |
|---------|----------------|
| **TEMPLATE** | Step type selection. Important when adding a step; less so when editing an existing one. Compact when selected. |
| **STEP** (metadata) | Display name, sequence, failure policy. Needed for identification and behavior, but users rarely tweak these after initial setup. |

### Tertiary (Power Users / Escape Hatch)

| Section | Why it matters |
|---------|----------------|
| **ADVANCED** | Raw JSON. For power users who need to override or inspect the full payload. Collapsible by default. |

---

## Proposed Section Order and Treatment

### 1. Top: Template (Compact)

- **Purpose:** Identify the step type. When a template is already selected, this can be a single compact row (trigger button or pill).
- **Treatment:** Minimal vertical footprint. See [p5_step-template-picker-architecture.md](./p5_step-template-picker-architecture.md) for the command-palette picker.
- **When prominent:** Only when the user is actively changing the template (overlay open).

### 2. Primary Block: Inputs, Configuration, Output

These sections form the **primary configuration block**. They should:

- Appear in this order: **INPUTS** → **CONFIGURATION** → **OUTPUT** (after **TEMPLATE**). *Rationale:* wire data sources first, then step-specific settings.
- Use the strongest visual treatment: clear section containers, ample padding, prominent headers
- Be separated by visible gaps (16–24px) so each stands out
- Use subtle background tint or borders to create distinct "cards"

**Rationale:** This is the main workflow. Users configuring a step spend most of their time here.

### 3. Secondary Block: Step Metadata

- **Content:** Display name, Sequence, Failure policy
- **Treatment:** Visually de-emphasized. Options:
  - **Option A:** Single compact section with smaller typography and reduced padding. Header: "STEP" or "IDENTIFICATION".
  - **Option B:** Collapsible by default (collapsed = "Step: Property Set · #1" or similar summary; expanded = full fields).
  - **Option C:** Placed at the bottom of the panel, above ADVANCED, so primary content appears first when scrolling.

**Recommendation:** Option A or C—keep metadata visible but compact. Avoid Option B if users need to see display name without expanding.

### 4. Bottom: Advanced

- **Treatment:** Collapsible, collapsed by default. Small header row when collapsed.
- **Content:** Raw JSON for power users.

---

## Visual Specification

### Section Order (Top to Bottom)

```
┌─────────────────────────────────────────────────────────────────┐
│  TEMPLATE (compact)                                              │
│  [Step template: Property Set ▼]   ← 1 line                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  INPUTS                          ← PRIMARY: prominent           │
│  ┌─────────────────────────────┐                                 │
│  │ value          step_google_places_lookup… [Select source]      │
│  └─────────────────────────────┘                                 │
│                                                                 │
│  CONFIGURATION                    ← PRIMARY: prominent           │
│  ┌─────────────────────────────┐                                 │
│  │ Target kind    [Schema property ▼]                           │
│  │ Property       [Name ▼]                                      │
│  └─────────────────────────────┘                                 │
│                                                                 │
│  OUTPUT                          ← PRIMARY: prominent           │
│  ┌─────────────────────────────┐                                 │
│  │ Preview of what this step produces...                         │
│  └─────────────────────────────┘                                 │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  STEP (secondary)                ← DEPRIORITIZED: compact        │
│  Display name · Sequence · Failure policy   [smaller, tighter]   │
├─────────────────────────────────────────────────────────────────┤
│  ADVANCED (collapsed)            [▼] Raw config                  │
└─────────────────────────────────────────────────────────────────┘
```

### Primary Section Styling (Inputs, Configuration, Output)

| Property | Specification |
|----------|---------------|
| **Background** | Subtle tint (e.g., `rgba(255,255,255,0.03)`) to create a soft card. |
| **Padding** | `14–18px` vertical, `18–22px` horizontal. |
| **Header** | Slightly larger, medium weight. Clear margin below (10–14px). |
| **Gap between sections** | `20–28px` between Inputs, Configuration, and Output. |

### Secondary Section Styling (Step Metadata)

| Property | Specification |
|----------|---------------|
| **Background** | None or very subtle (lighter than primary sections). |
| **Padding** | `8–12px` vertical, `14–18px` horizontal. |
| **Header** | Smaller than primary headers; more muted color. |
| **Fields** | Consider inline or compact layout (e.g., Display name | Sequence | Failure policy on one or two rows). |

### Label–Field Grouping (All Sections)

| Property | Specification |
|----------|---------------|
| **Label–input gap** | `4–6px` between label and its input. |
| **Field–field gap** | `12–16px` between field groups in primary sections; `8–12px` in secondary. |

---

## Implementation Approach

### Phase 1: Reorder and Restyle

1. **Reorder sections** in the inspector: Template (compact) → Inputs → Configuration → Output → Step (metadata) → Advanced.
2. **Apply primary styling** to Configuration, Inputs, Output: background, padding, header treatment.
3. **Apply secondary styling** to Step metadata: reduced padding, smaller typography, optional compact/inline layout.
4. **Ensure Output** has a visible preview (even if placeholder) so the section feels substantive.

### Phase 2: Compact Step Metadata

1. Evaluate whether Display name, Sequence, Failure policy can be rendered more compactly (e.g., two-column or inline).
2. Add a "STEP" section header that is visually lighter than primary headers.
3. Consider moving Step metadata below Output if it currently appears above primary content.

### Phase 3: Polish

1. Add design tokens for primary vs secondary section treatment.
2. Ensure Template section uses minimal space when picker is closed (per step-template-picker architecture).
3. Verify keyboard navigation and screen reader order match visual priority.

---

## Relationship to Other Docs

- **[p5_proposal-details-view-cleanup.md](./p5_proposal-details-view-cleanup.md)** — Defines section content. This doc proposes a *reordered* layout and *priority-based* visual treatment. The cleanup doc's section list remains the source of truth for what exists; this doc defines how to present it.
- **[p5_property-set-detail-view-architecture.md](./p5_property-set-detail-view-architecture.md)** — Property Set–specific Configuration. Configuration is the top-priority section; Property Set controls live there.
- **[p5_step-template-picker-architecture.md](./p5_step-template-picker-architecture.md)** — Template picker. The Template section should be compact when closed; this doc's deprioritization of Template (when selected) aligns with that.
- **[p5_pr01-style-guide-foundation.md](./p5_pr01-style-guide-foundation.md)** — Colors, typography, spacing. Primary/secondary treatment should use existing tokens where available.

---

## Acceptance Criteria

- [ ] Inputs, Configuration, and Output are visually prominent and appear in that order (after Template) near the top of the detail view.
- [ ] Step metadata (display name, sequence, failure policy) is visually de-emphasized—smaller, more compact, or placed below primary content.
- [ ] Template section is compact when a template is selected (single line or minimal footprint).
- [ ] Primary sections (Inputs, Configuration, Output) have stronger visual treatment than Step metadata (background, padding, header weight).
- [ ] Label–input pairs are visually grouped; spacing reinforces hierarchy.
- [ ] ADVANCED section is collapsible and collapsed by default.
- [ ] Changes work in dark mode and align with style guide.

---

## Resolved Decisions

| Decision | Choice |
|----------|--------|
| Primary sections | Inputs, Configuration, Output—in that order (after Template) |
| Step metadata treatment | Compact, secondary; reduced padding and typography |
| Section order | Template → Inputs → Configuration → Output → Step → Advanced |
| Template when selected | Minimal footprint; overlay for changing |
