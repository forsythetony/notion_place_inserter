# Admin-configurable theming and design tokens — research

Date: 2026-03-19

## Scope

**Product visual direction:** how we want configurable branding, palette structure, and admin editing to work, informed by common industry patterns. **Technical specification:** [p5_admin-runtime-theme-spec.md](../technical-architecture/productization-technical/phase-5-visual-editing/p5_admin-runtime-theme-spec.md). **Implementation tokens and UI component rules** stay in `notion_pipeliner_ui/styleguide/` per [README](./README.md).

### Single-app theming (current intent)

For **now**, treat appearance as **one global theme for the whole product**, editable **only by admins**. End users and separate “tenants” do **not** each get their own branding or token set. A possible **later** expansion: keep admin-defined tokens as the default, but allow **per-user** (or per-workspace) **overrides** on top of that baseline — that would be a separate feature and data model, not assumed here.

## Why this doc exists

You want an **admin-only** area to edit **global visual configuration** (colors, radii, typography, etc.) so the product can re-skin without redeploys, with **safe defaults**, **centralized** token definitions, optional **Figma / design-tool alignment**, **named presets** (including **JSON paste/import** for LLM-assisted authoring), and **defense in depth** (UI hidden for non-admins + API rejects unauthorized access).

This note surveys **how teams and products typically build that**, not a full implementation spec for this repo.

---

## Product intent (requirements snapshot)

| Theme | What you described |
|--------|-------------------|
| **Runtime theming** | Backend (or DB) holds theme config; frontend reads it and applies styles. |
| **Token-like model** | Primary / secondary / tints, button radii, font families — composed into a coherent palette. |
| **Single source of truth** | One canonical definition; components reference semantic tokens, not ad-hoc hex values. |
| **Admin UX** | Dedicated nav item visible only to admins; “dashboard” for palette + global settings. |
| **Authorization** | Double gate: no menu for non-admins; APIs return 403/401 if someone probes URLs. |
| **Overrides** | Defaults from palette; optional per-token overrides (e.g. graph-specific tweaks). |
| **Presets** | Save multiple themes; switch active theme; create from scratch. |
| **Import** | Paste structured JSON (e.g. from Cursor/another LLM) that matches a schema, validate, store. |

---

## How the industry usually models this

### 1) Design tokens (semantic layer over primitives)

Most mature systems separate:

- **Primitives** — raw values: `#2563eb`, `16px`, `Inter`, `0.375rem`.
- **Semantic tokens** — meaning in context: `color.action.primary`, `color.text.muted`, `radius.button.primary`.
- **Component tokens** (optional) — e.g. `button.primary.background` maps to semantic tokens.

That mirrors what you remember from “primary / secondary / secondary tint”: those are either **semantic** names or **brand ramps** (50–900 scales) derived from a few seed colors.

**References:**

- [Design Tokens Community Group (W3C)](https://design-tokens.github.io/community-group/format/) — common interchange format (JSON-friendly); tooling ecosystem converges here.
- [Style Dictionary](https://styledictionary.com/) — transform token JSON into CSS, iOS, Android, etc.; often used in build pipelines; can also be invoked programmatically if you ever generate static artifacts from admin-edited JSON.

Teams that need **admin/runtime** editing often **store tokens as JSON** (or rows) and **map them to CSS custom properties** at runtime rather than relying only on build-time Style Dictionary output.

### 2) Runtime delivery: CSS custom properties (`var(--token)`)

A widespread pattern for web apps:

1. Resolve active theme (preset) server-side or via API.
2. Emit one small payload: `{ "--color-primary": "...", "--radius-button": "..." }`.
3. Apply to `document.documentElement` (or a root wrapper) as inline style or a injected `<style>`.
4. Components use `var(--color-primary)` (in CSS, Tailwind arbitrary values, or a thin design-system wrapper).

**Why it’s popular:** one mechanism works across React trees, portals, and third-party widgets; no need to re-bundle CSS per tenant if the **variables** change.

**Alternatives:** theme objects in JS (e.g. CSS-in-JS libraries), or generating class maps at build time — those are harder to reconcile with **dynamic admin edits** unless you still bridge through CSS variables.

### 3) “Theme provider” in the frontend

UI frameworks often expose a **ThemeProvider** that supplies tokens to components:

- **Material UI (MUI)** — `createTheme`, component overrides; can be driven by fetched config.
- **Chakra UI** — semantic tokens and style props; theme is a JS object.
- **Radix Themes** — opinionated tokens + appearance.
- **shopify/p Polaris** — token set aimed at merchant admin UIs (more productized than a raw token editor, but illustrates **systematic** color/space/type roles).

The **admin page** you want is conceptually: “edit the object that the ThemeProvider would consume,” persisted remotely.

### 4) White-label / multi-tenant SaaS

B2B SaaS products often implement:

- **Per-tenant branding**: logo, favicon, primary color, sometimes full CSS.
- **Metadata-driven UI**: feature flags + branding config from a **tenant settings** service.

Blog/overview pieces that align with this direction (conceptual, not endorsements of specific vendors):

- [Multi-tenant theming overview (example blog)](https://www.qimu.dev/blog/2026-01-06-1-multi-tenant-theming) — tokens between env and components, per-tenant layering.
- [Metadata-driven UI customization (Medium)](https://sollybombe.medium.com/designing-metadata-driven-ui-customization-for-multi-tenant-saas-b13140221e5c) — central registry, real-time admin updates.

**Takeaway:** your “application configuration table” is standard; the differentiator is **schema quality** (semantic tokens, validation) and **how components consume** the config.

### 5) Merchant- or admin-facing “theme settings” in platforms

Examples users intuitively know:

- **Shopify themes** — settings schema in `config/settings_schema.json`, merchants edit in admin; theme liquid references `settings.*`. This is the **“nice settings panel + structured JSON”** mental model.
- **WordPress / site builders** — global styles + presets (Gutenberg `theme.json` is token-like JSON).

These reinforce your idea: **structured config + preview + save** beats unstructured “custom CSS” for consistency.

---

## Centralize configuration: practical patterns

### A) One registry, three consumers

1. **Canonical store** — DB JSON column or `app_theme` table (versioned rows), validated against a JSON Schema.
2. **API** — `GET /admin/theme/active`, `PUT /admin/theme/...` (admin-only); public app might only get **derived** CSS vars if you want to hide internal token names.
3. **UI** — admin editor + runtime `applyTheme()`.

### B) Layering defaults vs overrides

Common approach:

- **Base schema** — code-defined defaults (your “safe default”).
- **Preset / stored JSON** — overrides only keys that are set; merge with deep merge rules documented per key (replace vs append).
- **Graph-specific section** — namespaced keys, e.g. `overrides.reactFlow.edgeColor`, so the graph can diverge without forking the whole palette.

This matches “default to palette but let me override.”

### C) Validation and migration

- **JSON Schema** (draft 2020-12 or similar) for the blob you accept from humans *or* LLMs.
- **Version field** inside the blob (`schemaVersion: 2`) so you can migrate old presets when semantics change.
- **Sanitization** — still apply **structural** safety (schema, allowed types, maybe clamp radii to sane bounds, block dangerous patterns if raw CSS is ever allowed). **Do not** rewrite colors for contrast or accessibility: stored values are **exactly** what the admin set (see below).

### Contrast: exact values, no guarding

The product **does not** enforce WCAG contrast, block “bad” pairs, or auto-nudge colors to meet ratios. If an admin chooses combinations that are hard to read, **that is what ships**. Tests or tooling may still **warn** in the editor (optional, non-blocking); persistence and runtime apply the literal token values.

### Dark vs light: editor actions, not automatic runtime behavior

**Avoid:** deriving or flipping dark/light **silently** when the app loads, from system theme alone, or without the admin’s awareness.

**Prefer:** a **visible theme-editor workflow**, for example:

1. **Load** an existing preset.
2. **Duplicate** it (new draft preset).
3. Use an explicit control — e.g. **“Generate dark from this theme”** or **“Generate light from this theme”** — that runs **documented** transformation logic and fills in the duplicate’s tokens.
4. The admin **reviews** the result in the editor (and tweaks by hand or re-runs generation), then **saves**; only **saved** presets drive what end users see.

So algorithmic help is **opt-in and obvious** in the admin UI, not a hidden pipeline. The “active” theme for the app still points at **one** saved preset at a time (light-focused vs dark-focused presets can both exist; **user-facing** light/dark toggle, if any, is a separate product choice).

---

## Admin-only UX + double gating (your security model)

Typical implementation:

| Layer | Behavior |
|--------|-----------|
| **Frontend** | Route gated by auth claims (e.g. `role === admin`); nav item not rendered otherwise. |
| **Backend** | Every mutating route checks the same claim (or finer RBAC). No reliance on “hidden URL.” |
| **Read path** | Decide if **public** app needs only derived CSS vars vs full token object (least privilege). |

**Anti-patterns:** trusting `?admin=true`, or exposing PUT on a “public” `/theme` without auth.

---

## Presets, switching, and JSON paste (LLM-friendly)

### Patterns

- **Named presets** — rows: `id`, `name`, `config_json`, `created_at`, `is_system` (optional seed themes).
- **Active pointer** — `app_settings.active_theme_id` or environment-level default + tenant override later.
- **Import flow** — textarea → validate schema → preview diff → save as new preset → optionally “set active.”
- **Export** — copy JSON for backup or for LLM round-trips.

### Why JSON Schema matters for LLM paste

If you publish a **canonical example** + schema in-repo, tools like Cursor can generate payloads that validate first try. Consider:

- `$ref` to shared schema used by both backend validator and frontend form generator (optional advanced step).

---

## Figma / design-tool alignment

If you want tokens to stay in sync with design:

- **Figma Variables** — design owns ramps; export or sync to JSON (vendor scripts, or manual export).
- **Tokens Studio for Figma** — popular token workflows; integrates with [Style Dictionary transforms](https://docs.tokens.studio/transform-tokens/style-dictionary).

**Reality check:** continuous sync is a product of its own. Many teams **start** with:

1. One-time import from Figma export → preset JSON.
2. Admin edits in your app → optionally **export** for design review.

Your “extract from Figma” section on the admin page can mean **import pipeline**, not necessarily live API sync on day one.

---

## Trade-offs summary

| Approach | Pros | Cons |
|---------|------|------|
| **CSS variables from JSON** | Simple, framework-agnostic, instant apply | Need discipline so components don’t bypass tokens |
| **Build-time tokens only (Style Dictionary)** | Strong CI, multi-platform | Poor fit for on-the-fly admin edits unless combined with runtime layer |
| **Full CSS-in-JS theme object** | Typed, component-local | Harder to share with non-React islands; bundle coupling |
| **Raw custom CSS per tenant** | Maximum flexibility | Breaks consistency, security footguns |
| **LLM JSON import** | Fast iteration | Must validate strictly; document schema and migrations |

---

## Suggested direction (research conclusion, not a ticket)

1. **Treat theming as design tokens** with **semantic names**; store **JSON** + **schema version**.
2. **Apply at runtime** via **CSS custom properties** from a merged {defaults + preset} object.
3. **Admin UI** edits the same structure you accept on **import** (single schema).
4. **Authorize** theme mutations only on admin APIs; public read path exposes **minimal** data.
5. **Presets** as first-class rows; **active theme** as a pointer; optional **namespaced overrides** for graph/editor chrome.
6. **Contrast:** store and render **exact** admin/admin-imported values — **no** automatic contrast enforcement.
7. **Dark/light variants:** **no** hidden auto-theming; support **duplicate preset + explicit “generate dark/light” (or similar)** in the theme editor so transforms are **visible and intentional** before save.
8. **Figma** as **import/export** first; evaluate continuous sync only if design/engineering both need it.

---

## Further reading

- [Design Tokens W3C Community Group Format](https://design-tokens.github.io/community-group/format/)
- [Style Dictionary documentation](https://styledictionary.com/)
- [Tokens Studio ↔ Style Dictionary](https://docs.tokens.studio/transform-tokens/style-dictionary)
- Shopify — [Theme settings schema (concept reference)](https://shopify.dev/docs/storefronts/themes/architecture/settings) (illustrative of structured admin-editable theme config)
