# Architecture Proposal: Step Template Picker — Command-Palette-Style with Card Detail

Date: 2026-03-19  
Status: Proposed  
Owner: Product + Platform

## Problem

The current Step template selector in the inspector detail view consumes significant vertical space. The layout stacks:

- Section label (`TEMPLATE`)
- Field label (`Step template`)
- Dropdown control
- Output indicator bar
- Multi-line help/description text

For a single selection and its description, the component occupies a large vertical footprint. As the catalog grows (13+ step templates today), a dropdown also becomes harder to scan and discover. Users must open the dropdown to see options; there is no visual preview of what each step does before selection.

## Goals

- **Reduce vertical footprint** — Present the template picker more compactly without sacrificing clarity.
- **Preserve help text** — Keep the description/help text; it helps users understand what each step does.
- **Card-style navigation** — Square or card-like items for visual, scannable selection.
- **Fuzzy search** — Allow quick finding of the desired step by typing (e.g., "prop", "cache", "ai constrain").
- **Consistency** — Align with the broader inspector cleanup in [p5_proposal-details-view-cleanup.md](./p5_proposal-details-view-cleanup.md).

## Non-goals

- Changing the step template data model or API.
- Replacing the template picker entirely with a different paradigm (e.g., command palette only).
- Supporting drag-and-drop reordering of templates in the picker.
- Recent or favorites for frequently used templates (planned for later).

---

## Current Data Model

Step templates expose metadata suitable for cards and search:

| Field | Purpose |
|-------|---------|
| `id` | Unique identifier (e.g., `step_template_property_set`) |
| `display_name` | Human label (e.g., "Property Set") |
| `description` | Help text (e.g., "Write value to a specific target schema property or page metadata (icon/cover)") |
| `category` | Grouping (e.g., `output`, `transform`, `lookup`, `utility`) |

Templates are fetched via `GET /management/step-templates` (list) and `GET /management/step-templates/{template_id}` (detail). The list endpoint returns summary metadata; the detail endpoint returns full `config_schema`, `input_contract`, `output_contract`.

---

## Design: Command-Palette-Style Picker with Card Detail

A command-palette-style overlay that opens on demand, with a searchable list and a card detail panel. When closed, the inspector uses only a single line for the trigger control.

### Why This Approach

- **Maximizes inspector space** — When the picker is closed, the inspector dedicates minimal vertical space to template selection. The overlay borrows modal space instead.
- **Familiar pattern** — Command palettes (VS Code, Spotlight, Raycast, etc.) are well understood; users expect search-first interaction.
- **Fuzzy search is natural** — Typing to filter is the primary interaction; no need to scroll through a long dropdown.
- **Card detail on focus** — Users can browse options and see full help text without committing; the card detail panel provides context before selection.

---

### Closed State: Trigger Control

**Layout:** A single compact button or field in the Template section.

| Variant | Appearance | Behavior |
|---------|------------|----------|
| **Button** | "Choose step type" or "Property Set" (if selected) | Click opens overlay |
| **Compact field** | Pill/chip showing current template name + chevron | Click opens overlay |

**Vertical space:** ~1 line (40–48px). No dropdown, no output bar, no help text in the closed state.

**Keyboard:** When the trigger has focus, `Enter` or `Space` opens the overlay. Optional: `⌘K` / `Ctrl+K` from anywhere in the inspector opens the picker (if focus is on the step).

---

### Open State: Overlay

**Layout:** A modal overlay (not full-screen). Dimensions:

- **Width:** 480–560px (or 90% of viewport if narrower)
- **Height:** 320–400px (or auto, max 70vh)
- **Position:** Anchored to the inspector/trigger by default (e.g., below the trigger). Must be configurable so positioning can be switched to centered without code changes (e.g., via a prop, config flag, or theme setting).

**Overlay structure (grouped by category when search is empty):**

```
┌─────────────────────────────────────────────────────────────────┐
│  [⌘K] Search step templates...                              [×] │
├─────────────────────────────────────────────────────────────────┤
│  List (scrollable)              │  Card detail (optional)         │
│  ──────────────────────────    │  ───────────────────────────── │
│  OUTPUT                        │  Property Set                   │
│  ● Property Set                │  Output                         │
│    Write value to target...    │  Write value to a specific      │
│  TRANSFORM                     │  target schema property or      │
│  ○ AI Constrain Values         │  page metadata (icon/cover).    │
│    Select values from...       │                                 │
│  UTILITY                       │  Category: output               │
│  ○ Cache Set                   │                                 │
│    Store value into...         │                                 │
│  LOOKUP                        │                                 │
│  ○ Google Places Lookup        │                                 │
│    Perform Google Places...    │                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Two-panel layout (recommended):**
- **Left:** Searchable list (60–65% width). Each row: `display_name` + 1-line description snippet (~60 chars).
- **Right:** Card detail panel (35–40% width). Shows full content for the focused/selected row.

**Single-panel layout (simplified):**
- List only when space is tight. Card detail appears as tooltip on hover, or a compact block below the list when a row is focused.

---

### List Row Content

Each row in the list shows:

| Element | Content | Notes |
|---------|---------|-------|
| **Icon** | Category icon | Derived from `category` (output, transform, lookup, utility). One icon per category. |
| **Primary** | `display_name` | Bold or semibold |
| **Secondary** | First ~60 chars of `description` | Muted, single line, ellipsis |

**Icons:** Use category-level icons only (not per-template icons from catalog). Map each `category` value to a single icon. Per-template icons may be added later.

**Focus/hover:** Row highlights; card detail panel updates (if two-panel layout).

**Selection:** Row shows a checkmark or dot when it matches the current step's template.

---

### Card Detail Panel Content

When a list row is focused or hovered, the card detail panel shows:

| Section | Content |
|---------|---------|
| **Title** | `display_name` (with category icon) |
| **Description** | Full `description` (multi-line, wrapped) |
| **Category** | `category` with friendly label (e.g., "Output", "Transform", "Lookup", "Utility") |
| **Output** (optional) | Brief summary from `output_contract` (e.g., "Writes to target", "Returns `selected_values`") |

**Card styling:** Rounded corners, subtle border or background to separate from list. Padding sufficient for readability.

---

### Interaction Flow

1. **Open:** User clicks trigger or presses shortcut → overlay opens with focus in search bar.
2. **Search:** User types → list filters via fuzzy match. Focus remains in search bar; list updates in real time.
3. **Browse:** User presses `↓` / `↑` → focus moves to list; first (or last) row receives focus. Card detail updates.
4. **Select:** User presses `Enter` or clicks a row → template selected, overlay closes, inspector shows Configuration for that template.
5. **Cancel:** User presses `Escape` or clicks outside → overlay closes, no change.

**Keyboard shortcuts:**

| Key | Action |
|-----|--------|
| `↑` / `↓` | Move focus in list (when list has focus) |
| `Enter` | Select focused row |
| `Escape` | Close overlay, cancel |
| `Tab` | Move between search bar and list (optional) |

**Focus management:** When overlay opens, focus goes to search bar. Arrow keys can move focus into the list. When list has focus, typing should filter (consider: refocus to search when user types).

---

### Fuzzy Search Specification

- **Scope:** Match against `display_name`, `description`, `category`, `id`, and `slug`.
- **Algorithm:** Prefer simple substring match first; consider Fuse.js, fzf-style, or a lightweight tokenize-and-match implementation.
- **Behavior:**
  - Case-insensitive.
  - Partial matches rank higher when they match the start of a word.
  - **Empty query:** Show all templates grouped by `category`. Category headers (e.g., "Output", "Transform", "Lookup", "Utility") separate the list into sections.
  - **Non-empty query:** Flat list of matching templates (no category headers when filtering).
- **Performance:** Client-side filtering; ~15–30 templates, no server round-trip needed.
- **Typing while list focused:** Either refocus to search bar on keypress, or treat list focus as "search mode" and append to query.

---

### State Transitions

| State | Trigger | Result |
|-------|---------|--------|
| Closed → Open | Click trigger, Enter on trigger, ⌘K | Overlay opens, search focused |
| Open → Closed (select) | Enter on row, click row | Template selected, overlay closes, inspector updates |
| Open → Closed (cancel) | Escape, click outside | Overlay closes, no change |
| Open → Search | Type in search | List filters |
| Open → Browse | Arrow keys | List focus, card detail updates |

---

### Implementation Considerations

**Overlay positioning:**
- **Default:** Anchored — overlay opens below or beside the trigger; feels more connected to the inspector.
- **Configurable:** Support a positioning option (prop, config flag, or theme) so the overlay can be switched to centered without code changes. Centered mode floats the overlay over the graph + inspector.

**Responsive behavior:**
- Narrow viewport: Consider single-panel layout (list only), card detail as tooltip or collapse.
- Mobile: Full-width overlay; list may need larger touch targets.

**Accessibility:**
- Overlay role: `dialog` or `role="listbox"` with `aria-expanded`, `aria-activedescendant`.
- Focus trap: Focus stays within overlay until closed.
- Screen reader: Announce result count and "Search step templates" when opened.

**Data loading:**
- List data: Use `GET /management/step-templates` (already cached or fetched on inspector open).
- Card detail: Use list response; no extra fetch for detail unless we want richer `output_contract` summary.

---

### Alternatives Considered

| Option | Summary | Why not chosen |
|--------|---------|----------------|
| **A: Inline Card Grid** | Search bar + grid of cards in inspector | Uses more vertical space when open; grid always visible |
| **B: Compact Dropdown** | Searchable dropdown + collapsible help | Less visual; still dropdown-centric |
| **D: Horizontal Carousel** | Horizontal scroll of cards | Horizontal scroll can hide options; search becomes critical |

---

## Relationship to Other Docs

- **[p5_proposal-details-view-cleanup.md](./p5_proposal-details-view-cleanup.md)** — This proposal fulfills the "card-style step picker" mentioned as a future improvement. The cleanup doc currently recommends a "searchable dropdown" for the first pass; this document defines the command-palette upgrade path.
- **[p5_property-set-detail-view-architecture.md](./p5_property-set-detail-view-architecture.md)** — Applies after template selection. The Property Set-specific Configuration (write mode, property selector) is unchanged.

---

## Implementation Phases

### Phase 1: Overlay Shell + Searchable List
- Replace dropdown with trigger button/field.
- Implement overlay: search bar + list (no card detail yet). Anchored to trigger by default.
- Fuzzy search filters list. When search empty, group by category with section headers.
- Category icons per row (derived from template `category`).
- Keyboard: Enter to open, Escape to close, arrows to move.
- **Effort:** Medium. **Outcome:** Minimal vertical footprint, searchable selection.

### Phase 2: Card Detail Panel
- Add right-hand card detail panel.
- Update on list focus/hover.
- Show full description, category, optional output summary.
- **Effort:** Low–Medium. **Outcome:** Full card-style UX with help text.

### Phase 3: Polish
- Optional shortcut (⌘K) from inspector.
- Accessibility: ARIA, focus trap, screen reader announcements.
- Responsive: single-panel fallback for narrow viewports.
- Overlay positioning config (anchored vs centered).

---

## Acceptance Criteria

- [ ] When closed, the template picker uses ~1 line (trigger button or compact field).
- [ ] Clicking the trigger opens a command-palette-style overlay.
- [ ] Overlay is anchored to the inspector/trigger by default; positioning is configurable (anchored vs centered).
- [ ] Overlay contains a search bar and a scrollable list of step templates.
- [ ] When search is empty, list is grouped by category with section headers.
- [ ] When search has input, list shows flat filtered results (no category headers).
- [ ] Each list row shows category icon, `display_name`, and a short description snippet.
- [ ] Typing in the search bar filters the list via fuzzy match on name, description, category, id.
- [ ] A card detail panel shows full description, category, and optional output summary for the focused/hovered row.
- [ ] Pressing Enter or clicking a row selects the template and closes the overlay.
- [ ] Pressing Escape or clicking outside closes the overlay without changing the selection.
- [ ] Arrow keys move focus within the list.
- [ ] Vertical space in the inspector when picker is closed is less than the current stacked layout.

---

## Resolved Decisions

| Decision | Choice |
|----------|--------|
| Overlay position | Anchored by default; configurable to centered |
| Icons | Category icons only (derived from `category`) |
| Recent/favorites | Not supported; planned for later |
| Category grouping | Yes, when search is empty |
