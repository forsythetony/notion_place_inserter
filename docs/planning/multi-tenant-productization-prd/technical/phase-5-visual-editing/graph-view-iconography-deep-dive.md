# Graph View Iconography Deep Dive

Date: 2026-03-18  
Status: Proposed

## Objective

Make the graph view easier to scan by replacing repeated text with a small, consistent icon system. The goal is to convey step type, integration/provider, and status more quickly without making nodes feel crowded.

## Why this matters

The graph view is currently text-heavy. That creates a few problems:

- repeated labels consume horizontal space that could be used for layout clarity
- similar-looking nodes are harder to distinguish at a glance
- provider identity is easy to miss unless the user reads the full label
- zoomed-out views lose meaning quickly because text truncates before structure does

This is a strong fit for iconography, but only if we keep the system disciplined. The graph should not become a wall of mixed visual styles or brand logos with inconsistent sizes.

## Design principle

Do not replace all text. Replace repeated text.

The graph should keep one primary textual anchor per node, then use icons for the metadata that users repeatedly scan for:

- `step template`
- `provider / company`
- `status / warnings`

That means:

- keep the user-authored or pipeline-authored display name visible
- shorten or remove repeated step-template text in the dense graph view
- move fuller descriptions to hover, tooltip, or inspector surfaces

## Current implementation context

Based on the current repo state:

- the frontend graph implementation is not checked in here, but the data model and editor APIs are
- the step-template list API currently returns `id`, `display_name`, `category`, `status`, and `description`
- the connections list API returns `connector_template_id` and related connection metadata
- step templates already have stable identifiers like `step_template_google_places_lookup`
- connector templates already have stable identifiers and providers like `notion_oauth_workspace`, `google_places_api`, and `claude_api`

This gives us good mapping keys today, even without storing any icon metadata in the backend yet.

## What should get an icon

### 1. Step template icon

Each step node should have a primary icon tied to `step_template_id`.

Examples:

- `step_template_google_places_lookup` -> map/search icon
- `step_template_property_set` -> form/edit icon
- `step_template_cache_get` and `step_template_cache_set` -> database or hard-drive icon
- `step_template_ai_prompt` / `step_template_optimize_input_claude` -> sparkle, wand, or brain-like AI icon
- `step_template_upload_image_to_notion` -> image upload icon

### 2. Provider or company icon

Where a step or connected system is strongly tied to a provider, show a smaller provider badge:

- Notion
- Google
- Anthropic / Claude

This is especially useful for:

- steps whose runtime depends on a specific external provider
- connection nodes or chips
- inspector headers and node footers

### 3. Status icon

Use tiny status indicators for:

- validation issue
- warning
- active / inactive
- saving / synced

These should be semantic UI icons, not brand icons.

## Open-source icon pack recommendation

We use two icon sources with clearly separated responsibilities. **Use React providers wherever available** so icons integrate cleanly with the component tree and benefit from tree-shaking.

| Use case | Recommendation | React package | Why |
|---|---|---|---|---|
| General product/system icons | `Lucide` | `lucide-react` | Clean stroke style, React components, tree-shakeable, open source (`ISC`) |
| Brand/provider logos | `Simple Icons` | `@icons-pack/react-simple-icons` | Large catalog of company marks, open source (`CC0` core; React wrapper available) |

### Recommended approach

- **Lucide** (`lucide-react`) — primary for all graph/system icons (step templates, status, UI actions)
- **Simple Icons** (`@icons-pack/react-simple-icons`) — backup/secondary for provider/company identity only (Notion, Google, Anthropic, etc.)

Use the official React packages so icons render as components and participate in the app's provider/context system. Avoid importing raw SVGs or icon fonts when a React provider exists.

## Styling recommendation

The icon source can be mixed, but the presentation should be unified.

Recommended node treatment:

- step icon in a fixed-size badge, for example `18px` icon inside a `24px` or `28px` container
- provider logo as a secondary badge, smaller than the step icon
- one-color or duotone treatment in the graph canvas, not full raw brand colors everywhere
- reserve full brand color usage for inspector headers, connection lists, or onboarding surfaces

This matters because full-color brand logos can quickly overpower a dense node graph.

### Graph-specific rule

On the graph canvas:

- prefer monochrome or lightly tinted provider logos
- use accent color sparingly for state and selection
- keep icon stroke/weight visually aligned with the Calm Graphite design direction

## Suggested node layout

For dense graph mode, a step node could look like:

1. leading step-template icon
2. short display name
3. optional provider badge
4. optional status badge

The current long step-template label can move to:

- tooltip
- inspector title/subtitle
- searchable add-step menu

This keeps the canvas readable while still preserving discoverability.

## Mapping key recommendation

Use the most stable semantic keys available:

### Step nodes

Primary key: `step_template_id`  
Fallback key: `category`

`step_template_id` is the right default because it is:

- stable
- explicit
- already used across the model
- more precise than `display_name`

### Provider / integration badges

Primary key: `connector_template_id`  
Fallback key: `provider`

This lets us show the exact provider logo when we know it, and a generic provider/category mark when we do not.

## Where should mappings live?

There are three viable approaches.

### Option A. Store mappings in the frontend

Example: `graphVisualRegistry.ts`

Pros:

- fastest path to implementation
- easy to version with UI code
- no backend or migration work required
- best fit when the icon system is mostly presentation concern
- safest when the mapping set is small and changes infrequently

Cons:

- frontend deploy required for every icon mapping change
- multiple clients could drift if we later add more frontends
- harder for non-engineers to change without a code release

### Option B. Store mappings in the database

Example: per-step-template visual metadata or a dedicated visual registry table

Pros:

- central source of truth across clients
- allows runtime updates without a frontend redeploy
- opens the door to admin-configurable visuals later

Cons:

- more backend and schema complexity
- requires validation so bad icon keys do not break the UI
- mixes presentation metadata into the data model earlier than we may need
- increases coupling between backend contracts and UI styling decisions

### Option C. Hybrid

Store default mappings in the frontend, and optionally allow backend overrides later.

Pros:

- fast to ship now
- preserves a path to centralized management later
- keeps the initial implementation simple

Cons:

- slightly more design work up front because we need override rules
- can become confusing if override precedence is not explicit

## Recommendation

Start with **Option A: frontend-owned mappings**, with the code structured so it can evolve into **Option C: hybrid overrides** later.

Reasoning:

- the mapping set is currently small
- the strongest keys already exist in the frontend-facing data
- the graph view styling is a presentation concern first, not a domain concern
- we should avoid adding database complexity until we know the icon system is stable

## Recommended implementation shape

In the frontend, define a small visual registry keyed by semantic IDs, not by display text.

```ts
type StepVisualSpec = {
  icon: string;
  shortLabel?: string;
  tone?: 'neutral' | 'accent' | 'success' | 'warning';
  providerLogo?: string | null;
};

type ConnectorVisualSpec = {
  logo: string;
  monochromeOnCanvas?: boolean;
};

export const STEP_TEMPLATE_VISUALS: Record<string, StepVisualSpec> = {
  step_template_google_places_lookup: {
    icon: 'map-pinned',
    shortLabel: 'Lookup',
    providerLogo: 'google',
  },
  step_template_property_set: {
    icon: 'square-pen',
    shortLabel: 'Set property',
  },
  step_template_ai_prompt: {
    icon: 'sparkles',
    shortLabel: 'AI prompt',
    providerLogo: 'anthropic',
  },
};

export const CONNECTOR_TEMPLATE_VISUALS: Record<string, ConnectorVisualSpec> = {
  notion_oauth_workspace: { logo: 'notion', monochromeOnCanvas: true },
  google_places_api: { logo: 'google', monochromeOnCanvas: true },
  claude_api: { logo: 'anthropic', monochromeOnCanvas: true },
};
```

Important guardrails:

- do not key this map by `display_name`
- do not store raw SVG blobs in the database for the first iteration
- do store semantic icon keys that resolve through a single shared icon component
- resolve Lucide keys via `lucide-react` components; resolve Simple Icons keys via `@icons-pack/react-simple-icons` components

## If we later move some of this into the backend

If we decide central management is worth it later, the backend should store semantic references, not presentation assets:

- `icon_key`
- `logo_key`
- `tone`
- `short_label`

Avoid storing:

- raw SVG payloads
- arbitrary icon pack markup
- per-client styling rules

That keeps the contract portable and reduces security/styling risk.

## Rollout plan

### Phase 1. Dense graph cleanup

- add step-template icons to nodes
- keep display name text
- move long template names out of the main graph row

### Phase 2. Provider identity

- add small provider badges for Notion, Google, Anthropic-backed steps and connections
- standardize monochrome-on-canvas treatment

### Phase 3. Optional backend overrides

- only if we need runtime configurability or cross-client consistency

## Final recommendation

To make the graph view feel nicer, more consistent, and more informative without crowding:

- use **Lucide** (`lucide-react`) as the default UI/system icon pack
- use **Simple Icons** (`@icons-pack/react-simple-icons`) for company/provider logos only
- use React providers/components where available — avoid raw SVG imports when a React package exists
- map visuals in the frontend first, keyed by `step_template_id` and `connector_template_id`
- keep one line of meaningful text per node, but replace repeated metadata labels with icons
- treat brand logos in a restrained, mostly monochrome way on the canvas

This gives us a cleaner graph immediately, keeps the implementation simple, and leaves room to centralize the mapping later if the product needs it.
