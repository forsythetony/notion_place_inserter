# p5 — Admin runtime theme (technical specification)

| Field | Value |
|--------|--------|
| Status | Draft spec (implementation not started) |
| Date | 2026-03-19 |
| Last revised | 2026-03-21 — §10.5 **frontend codebase audit** (global vs graph-specific styling); prior: 2026-03-19 admin-page plan; **single-page theme consumption pilot** (no global shell) |
| Product direction | [Admin theming / tokens research](../../../style/admin-theming-design-tokens-research.md) |

## 1. Purpose

Deliver **one global UI theme** for the whole product, **editable only by admins**, persisted in **Postgres**, exposed to the **Notion Pipeliner UI** via APIs, and applied at runtime (primarily via **CSS custom properties**). Non-admin users never see the editor; unauthorized API calls are rejected.

This spec is implementable in **this repo** (FastAPI + Supabase Postgres) and the **sibling** `notion_pipeliner_ui` repo (admin page + **scoped** theme application).

### 1.1 Rollout principle: one consuming page at a time

To limit blast radius, **v1 implementation must not** apply runtime CSS variables globally (no `App.tsx` / `AppShell` / root layout hook that affects every route).

Instead:

1. Ship the **backend** (migration, merge, `GET /theme/runtime`, admin CRUD) and the **admin Theme editor** route.
2. Pick **exactly one** “pilot” product route (e.g. `/pipelines` — **choose and record in the implementation PR**). Only that route’s component tree loads `GET /theme/runtime` and applies returned `cssVars`.
3. Apply variables to a **route-local wrapper element** (e.g. the top-level `div` for that page), **not** to `document.documentElement`, unless/until a later phase moves to global shell application.

All **other** routes keep today’s styling; they **must not** import the runtime-theme hook or depend on `--pipeliner-*` until explicitly migrated in a follow-up task.

**Admin editor preview:** The editor page may apply resolved tokens inside a **preview subtree** (same pattern: wrapper `div` + inline `cssVars`, or an iframe pointed at a minimal preview shell). That preview must **not** change globals either.

## 2. Goals

- **G1.** Admins can create, rename, duplicate, delete (non-system), and **set active** theme presets stored as versioned JSON.
- **G2.** Edit the **same JSON shape** via form fields, raw JSON paste (validated), and export for LLM round-trips.
- **G3.** **Structural validation** on save/import (schema, types, bounds where agreed); **no** WCAG/contrast auto-correction — stored values are **literal**.
- **G4.** **Explicit** dark/light helpers in the **admin editor** only (duplicate + “generate …” action); **no** silent system-wide theme flip on app load.
- **G5.** Any authenticated app user can read **resolved runtime** payload for the active preset (merged with code defaults); only **ADMIN** (`user_type` in `user_profiles`) can mutate presets or the active pointer.
- **G6.** Double gate: admin UI hidden for non-admins; backend enforces the same on all mutating routes.

## 3. Non-goals (v1)

- Per-tenant / per-owner branding (single global theme only).
- End-user ability to override admin theme (possible future phase).
- Continuous Figma sync (import/export manually or one-off scripts is enough for v1).
- Serving arbitrary user-uploaded font binaries (use system stack or hosted font URLs if added later — decide in implementation).
- Automatic dark mode driven only by `prefers-color-scheme` without an admin-saved preset.

## 4. Architecture

```mermaid
flowchart LR
  subgraph admin [Admin browser]
    Editor[Theme editor page]
  end
  subgraph api [FastAPI API]
    AdminRoutes["/management/ui-theme/*"]
    PublicRoute["/theme/runtime"]
    ThemeSvc[Theme service]
    AdminRoutes --> ThemeSvc
    PublicRoute --> ThemeSvc
  end
  subgraph db [Supabase Postgres]
    Presets[ui_theme_presets]
    Pointer[app_ui_theme_settings]
  end
  Editor --> AdminRoutes
  subgraph app [Pilot route only (v1)]
    PilotPage[Single page wrapper applies cssVars]
  end
  PublicRoute --> PilotPage
  ThemeSvc --> Presets
  ThemeSvc --> Pointer
```

- **Canonical data** lives in `ui_theme_presets` + `app_ui_theme_settings`.
- **Code defaults** live in the API (Python module), merged at read time with the active preset’s `config` (see §7).
- **Runtime output** for the SPA is a small JSON object the client uses to set CSS variables on a **scoped element** for the pilot route (and for editor preview). **Global `:root` application is a later rollout phase**, not v1.

## 5. Data model

### 5.1 Tables

**`ui_theme_presets`**

| Column | Type | Notes |
|--------|------|--------|
| `id` | `uuid` | PK, `gen_random_uuid()` |
| `name` | `text` | Display name, `NOT NULL` |
| `config` | `jsonb` | Token document; must validate against v1 schema (§6) |
| `is_system` | `boolean` | Default `false`; if `true`, DELETE disabled via API |
| `created_at` | `timestamptz` | Default `now()` |
| `updated_at` | `timestamptz` | Maintained by API |
| `created_by_user_id` | `uuid` | Nullable FK → `auth.users(id)` |

Index: optional `CREATE INDEX ON ui_theme_presets (updated_at DESC)` for admin list sorting.

**`app_ui_theme_settings`** (singleton)

| Column | Type | Notes |
|--------|------|--------|
| `id` | `smallint` | PK, fixed `CHECK (id = 1)` |
| `active_preset_id` | `uuid` | Nullable FK → `ui_theme_presets(id)` `ON DELETE SET NULL` |
| `updated_at` | `timestamptz` | Default `now()` |

Bootstrap migration: `INSERT INTO app_ui_theme_settings (id) VALUES (1)` so the pointer row always exists.

### 5.2 RLS

Policies must align with existing auth: JWT identifies `auth.uid()`, profile row gives `user_type`.

Recommended policy sketch (exact SQL in migration PR):

- **`ui_theme_presets`**: `SELECT` allowed for **`authenticated`** (any logged-in user needs to resolve theme) **or** restrict `SELECT` to active preset only via RPC/view — simpler v1: allow `SELECT` on all presets for **authenticated** only; admins see full list via same table (names leak non-active preset names to all users — acceptable for v1 **or** tighten with “public read uses `theme/runtime` only” and revoke direct table SELECT from `authenticated`; then only **service role** / SECURITY DEFINER RPC exposes resolved payload).  
  **Recommendation for v1:** do **not** expose table read to clients; only the **API** uses Supabase with a key that can read presets (today: verify whether `main.py` uses **service role** or **user JWT** for PostgREST). If the Python API uses the **service role** for all DB access, RLS is bypassed and **all** authorization stays in FastAPI (`require_admin_managed_auth` vs `require_managed_auth`). Document the chosen client in the implementation PR.
- **Mutations** on presets and singleton: only if using user-scoped client, restrict `INSERT`/`UPDATE`/`DELETE` to `user_profiles.user_type = 'ADMIN'`.

**Corollary:** If the backend continues to use **service role** for repositories, implement **all** admin checks in FastAPI only; migrations still add tables and optionally RLS for future direct Supabase access.

### 5.3 Seeding

Optional: migration or seed script inserts one `is_system = true` preset named e.g. “Default (Calm Graphite)” whose `config` matches current product defaults, and sets `active_preset_id` to that preset’s id.

## 6. Config schema (v1)

### 6.1 Top-level shape

Store in `config` (and accept on import):

```json
{
  "schemaVersion": 1,
  "tokens": {
    "color": {},
    "radius": {},
    "typography": {},
    "graph": {}
  }
}
```

- **`schemaVersion`**: integer; bump when breaking semantics. Migration code in the API maps older versions when loading.
- **`tokens`**: semantic grouping; exact keys are extended over the productization without breaking `schemaVersion` when possible (additive). Breaking renames require a version bump + migrator.

### 6.2 Initial key set (illustrative — finalize with design)

These names are **indicative**; lock the first catalog with `notion_pipeliner_ui/styleguide` before shipping.

| Path | Example | Notes |
|------|---------|--------|
| `tokens.color.primary` | `"#2d3748"` | Brand primary |
| `tokens.color.secondary` | `"#4a5568"` | Brand secondary |
| `tokens.color.secondaryTint` | `"#718096"` | Tint / muted brand |
| `tokens.color.surface` | `"#f7fafc"` | Page / panel background |
| `tokens.color.text` | `"#1a202c"` | Primary text |
| `tokens.radius.buttonPrimary` | `"8px"` | Primary button |
| `tokens.radius.buttonSecondary` | `"6px"` | Secondary button |
| `tokens.typography.fontFamilySans` | `"Inter, system-ui, sans-serif"` | |
| `tokens.graph.edgeStroke` | `"#a0aec0"` | Graph-specific override namespace |

**Structural validation (always):**

- Reject unknown top-level keys if the validator is strict, **or** allow unknown nested keys under `tokens` for forward compatibility (recommended: allow unknown keys under `tokens.*` but validate **known** keys’ types).
- `schemaVersion` required, positive int.
- Colors: string format (hex `#RRGGBB` / `#RRGGBBAA` or agreed list); no rewriting.
- Radii: string suffix `px` or `rem`, optional max clamp **only if** product decides (document clamp values in code — **never** derive from contrast).

**Artifacts in repo:**

- `product_model/...` or `schemas/ui_theme_config_v1.json` — **JSON Schema** for validation (shared conceptually with frontend).
- Example preset in docs or seed for LLM paste.

### 6.3 Dark/light “generate” semantics

- Implemented as **editor-only** behavior: either **client-side** TS function or **`POST /management/ui-theme/actions/preview-derived`** returning **unsaved** `config` JSON for review.
- Must be **documented**: deterministic mapping rules (e.g. which `tokens.color.*` roles swap to dark surfaces). Not applied until admin saves a preset.
- **No** endpoint applies derivation automatically on `GET /theme/runtime`.

## 7. Merge and resolution

**Default merge order** when producing runtime tokens:

1. Start from **`DEFAULT_THEME_TOKENS`** in Python (full v1 tree).
2. Deep-merge **active preset** `config.tokens` over defaults (preset wins on leaf conflicts).
3. **No** contrast or accessibility post-processing.

**`GET /theme/runtime`** returns:

```json
{
  "schemaVersion": 1,
  "presetId": "uuid-or-null",
  "cssVars": {
    "--pipeliner-color-primary": "#2d3748",
    "--pipeliner-radius-button-primary": "8px"
  }
}
```

- **`presetId`**: `null` if no active preset (pure defaults).
- **`cssVars`**: flattened, stable, prefixed with `--pipeliner-` (or agreed prefix) to avoid collisions. Mapping table `TOKEN_PATH → css var name` lives in one Python module and is documented for the frontend.

Optional second field `tokens` (nested merged object) for debugging — **omit in production** or gate behind admin-only query param; prefer **cssVars-only** for least surprise.

## 8. API

Base URL same as existing management API. Auth: **Bearer** Supabase JWT.

### 8.1 Public / standard user

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/theme/runtime` | `require_managed_auth` | Returns merged `cssVars` + metadata for shell |

**Rationale:** matches existing dashboard pattern (Bearer required). Login page before auth can keep static CSS until token is available; **follow-up** could add anonymous `GET` if marketing needs branded login.

### 8.2 Admin (`require_admin_managed_auth`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/management/ui-theme/presets` | List presets: `id`, `name`, `is_system`, `updated_at` (no full `config` in list) |
| `POST` | `/management/ui-theme/presets` | Body: `{ "name": "...", "config": { ... } }` — create |
| `GET` | `/management/ui-theme/presets/{preset_id}` | Full preset including `config` |
| `PUT` | `/management/ui-theme/presets/{preset_id}` | Replace `name` and/or `config` |
| `DELETE` | `/management/ui-theme/presets/{preset_id}` | 403 if `is_system`, else delete |
| `POST` | `/management/ui-theme/presets/{preset_id}/duplicate` | Body optional `name`; creates copy with new id |
| `PUT` | `/management/ui-theme/active` | Body: `{ "preset_id": "uuid" \| null }` — set active pointer |
| `GET` | `/management/ui-theme/active` | Same resolution as runtime but include raw `config` for editor |

Optional:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/management/ui-theme/actions/preview-derived` | Body: `{ "base_config": {...}, "target": "dark" \| "light" }` → `{ "config": {...} }` unsaved |

**Errors:** `422` with `validation_errors[]` on schema failure (align with existing management validation style); `404` unknown preset; `403` non-admin or system preset delete.

### 8.3 OpenAPI

Extend existing OpenAPI doc generation to include the new routes and Bearer security.

## 9. Backend implementation notes

- **Router:** e.g. `app/routes/ui_theme.runtime.py` + `app/routes/ui_theme.management.py` or single module with two routers; register in `app/main.py`.
- **Repository:** e.g. `PostgresUiThemeRepository` in `postgres_repositories.py` (or dedicated file) using existing Supabase client patterns.
- **Service:** `UiThemeService` — validate config, merge defaults, map to `cssVars`, handle `preview-derived`.
- **Validation:** Prefer **Pydantic** models mirroring v1 + optional `jsonschema` if LLM paste requires shared schema file; keep one source of truth.
- **Dependencies:** add only if needed (e.g. `jsonschema`); avoid heavy deps.

## 10. Frontend (`notion_pipeliner_ui`)

### 10.1 Admin Theme editor route (explicit build plan)

**Path:** e.g. `/admin/theme` or `/settings/theme` (pick one; use the same path in `App.tsx` router and nav).

**Visibility:** Nav item and route guard: **only** if `user_type === 'ADMIN'` (same source as other admin features). Non-admins get 404 or redirect to home — **do not** leak preset names in the UI.

**API client (`src/lib/api.ts` or sibling):** Add typed functions that call the backend with the existing Bearer helper:

| Client function | HTTP | Purpose |
|----------------|------|---------|
| `fetchUiThemeRuntime()` | `GET /theme/runtime` | Resolved `cssVars` for preview + pilot page |
| `listUiThemePresets()` | `GET /management/ui-theme/presets` | Table rows |
| `getUiThemePreset(id)` | `GET /management/ui-theme/presets/{id}` | Full `config` for editor |
| `createUiThemePreset(body)` | `POST /management/ui-theme/presets` | Create |
| `updateUiThemePreset(id, body)` | `PUT /management/ui-theme/presets/{id}` | Save |
| `deleteUiThemePreset(id)` | `DELETE` … | Non-system only |
| `duplicateUiThemePreset(id, name?)` | `POST …/duplicate` | Copy |
| `getUiThemeActive()` | `GET /management/ui-theme/active` | Editor “active” banner + conflict hints |
| `setUiThemeActivePreset(presetId \| null)` | `PUT /management/ui-theme/active` | Set global active pointer |
| `previewDerivedUiThemeConfig(body)` | `POST …/actions/preview-derived` | Optional; dark/light helper |

**Page component structure (single file or small folder):**

1. **Load on mount:** `listUiThemePresets()` → populate left **preset list** (name, `is_system`, `updated_at`, badge if id matches active from `getUiThemeActive()` or from list + separate active call).
2. **Selection:** Clicking a row calls `getUiThemePreset(id)` → set **editor state** `{ name, config, dirty }`.
3. **Active preset:** Toolbar shows **“Active for app”** with `setUiThemeActivePreset`. Changing active must **not** auto-navigate away; show toast on success. Optimistic UI optional; on failure refetch.
4. **Create:** “New preset” → optional name prompt → `createUiThemePreset` with `config` copied from current selection or empty template from a **typed TS default** mirroring v1 shape (same keys as `DEFAULT_THEME_TOKENS` conceptually).
5. **Save:** `updateUiThemePreset` when dirty; surface `422` `validation_errors[]` inline.
6. **Delete:** Confirm dialog; disable for `is_system`.
7. **Duplicate:** `duplicateUiThemePreset`; select the new row after success.
8. **JSON editing:** Secondary panel: textarea or editor bound to `JSON.stringify(config, null, 2)` with parse-on-blur; invalid JSON blocks save with inline error (client-side); server remains source of truth on submit.
9. **Form fields (incremental):** Start with a **minimal** subset of `tokens.*` (e.g. primary/surface/text) as color inputs; keep **one** `config` object in React state — forms and JSON stay in sync (form updates `config`; JSON panel replaces whole `config` on valid parse).
10. **Preview region:** A `div` with `style={cssVarsFromRuntime}` where `cssVarsFromRuntime` is either:
    - **`fetchUiThemeRuntime()`** after each successful save / set-active (shows **live active** theme), **or**
    - local merge preview: **unsaved** `config` merged in the browser only for preview (optional v1; can defer and only preview active-from-server).

   **Rule:** Preview `div` is **self-contained**; do not set variables on `:root` from this page.

**Empty / error states:** Loading skeleton; empty preset list + CTA to create; network error banner with retry.

**Files to add/touch (expectation for implementers):**

- `src/routes/AdminThemePage.tsx` (or `ThemeSettingsPage.tsx`) — main UI
- `src/lib/api.ts` — API wrappers above
- `src/layouts/AppShell.tsx` (or nav config) — **one** admin nav link, gated
- Router registration — **one** new route

**Out of scope for the editor PR:** Refactoring unrelated pages, global MUI theme sync, or changing `index.css` except where needed for the **pilot** page (see §10.2).

### 10.2 Pilot route: exactly one consuming page

**Choice:** The implementation PR **must** name the single pilot path (e.g. `/pipelines`). Until a follow-up epic, **no other route** may call `fetchUiThemeRuntime()` or apply `--pipeliner-*`.

**Implementation pattern:**

- Add a small hook, e.g. `useRuntimeUiTheme()`, that:
  - Calls `GET /theme/runtime` when the pilot route **mounts**
  - Returns `{ cssVars, loading, error }` and applies nothing by itself
- Pilot page root:

```tsx
const { cssVars, loading } = useRuntimeUiTheme();
return (
  <div className="pipeliner-theme-pilot-root" style={cssVars}>
    {/* existing page content */}
  </div>
);
```

- **CSS:** Only **this page’s** components should use `var(--pipeliner-…)` for the properties being piloted (start with 1–3 tokens, e.g. background + primary + text). Other pages keep hard-coded / existing tokens.

**Leaving the pilot route:** Unmounting removes the wrapper; variables no longer apply to the rest of the app (no cleanup of `:root` required).

### 10.3 Later phase (not v1)

- Global shell: after login, one `GET /theme/runtime` in `AppShell` and `cssVars` on `:root`.
- Broader component migration per the styleguide.

### 10.4 Style guide

New `--pipeliner-*` names must be documented in `notion_pipeliner_ui/styleguide/` as they are introduced; **pilot page** only references the first batch.

### 10.5 Frontend codebase audit — global theming vs graph-specific styling

This section records a **2026-03-21** pass over `notion_pipeliner_ui` so implementers know **where** runtime tokens will land first, **what** should stay in a **`tokens.graph.*`** namespace (see §6.2), and **what** is layout coupling rather than color.

#### 10.5.1 Current layering

| Layer | Role | Notes |
|--------|------|--------|
| `src/index.css` | `:root` **Calm Graphite** palette | Defines `--background`, `--surface-1`, `--surface-2`, `--border`, `--text-primary`, `--text-secondary`, `--accent`, `--success`, `--warning`, `--danger`, aliases (`--text`, `--bg`, `--code-bg`, `--accent-bg`, `--accent-border`, `--shadow`), typography (`--sans`, `--heading`, `--mono`). |
| `src/App.css` | Most product UI | Mix of `var(--…)` usage and **literal** colors; largest file; management pages, pipeline editor, triggers, live-test modals, trigger body editor, etc. |
| `@xyflow/react/dist/style.css` | React Flow defaults | Imported from `PipelineEditorPlaceholder.tsx`; controls default **edges**, **handles**, internal chrome unless overridden. |

**Already aligned with general tokens (examples):** App shell / sidebar / top bar; most `.pipeline-editor-node*` surfaces and borders; `ProviderLogo` uses `currentColor` when monochrome (inherits parent text color).

#### 10.5.2 Candidates to migrate toward global / runtime tokens

These are **not** graph-canvas-specific; they should eventually map to **`tokens.color.*`**, **`tokens.radius.*`**, **`tokens.typography.*`**, and their **`--pipeliner-*` CSS outputs**, or to **consolidated `:root` aliases** before runtime ships.

1. **Literal RGB / “Tailwind-style” colors in `App.css`** — e.g. fixed reds/greens/yellows (`rgb(239, 68, 68)`, `rgb(34, 197, 94)`, `rgb(234, 179, 8)`) for validation, field errors, and schema row emphasis. Prefer **semantic tokens** (`--danger`, `--success`, `--warning`) plus optional **muted variants** (e.g. `color-mix` or dedicated `--*-muted` in the preset).
2. **Duplicate fallbacks** — patterns like `var(--danger, #dc3545)` where `index.css` already defines `--danger`. Collapse to a single source to avoid drift from admin presets.
3. **Light-theme literals inside a dark app** — e.g. `#0F1520`, `#fff` in some management/form paths. Either fold into **`--text-*` / `--surface-*`** or introduce explicit **inverted / “card on chrome”** roles in the v1 token catalog.
4. **Repeated scrims and elevation** — `rgba(0, 0, 0, 0.4–0.6)` overlays and similar `box-shadow` stacks. Candidates for **`--overlay-scrim`**, **`--shadow-sm`**, **`--shadow-lg`** (or equivalent in `tokens.color` / structural groups).
5. **CSS variables referenced in `App.css` but not defined in `index.css :root`** — examples observed: `--primary` (focus outline; **no** `--primary` in `index.css` — app uses `--accent` elsewhere), `--surface-0`, `--surface-alt`, `--surface-hover`, `--surface`, `--muted`, `--font-mono` vs `--mono`. **Resolution:** add them to the **code default** tree (`DEFAULT_THEME_TOKENS`) and/or `index.css` so presets and fallbacks stay consistent.
6. **Gradients with literal brand hues** — e.g. trigger/target node backgrounds mixing `rgba(59, 130, 246, 0.1)` or `rgba(34, 197, 94, 0.08)` with `var(--surface-1)`. Prefer **`color-mix(in srgb, var(--accent) …)`** (and success analog) so they track the active preset.
7. **Inline `style={{}}` in TSX** — minimal today (`ConnectionsPage`, `DataTargetsPage` layout only); low priority; optional utility classes later.

#### 10.5.3 Graph / pipeline canvas — prefer explicit `tokens.graph.*`

Keep **diagram semantics** separate from generic form chrome so admins can tune “edges read on dark gray” without breaking buttons site-wide. The v1 schema already reserves **`tokens.graph.*`** (§6.2, e.g. `edgeStroke`).

| Concern | Why it’s specific | Direction |
|---------|-------------------|-----------|
| **XYFlow default stylesheet** | Library colors for edges, handles, connection line | Scoped CSS overrides under **`.pipeline-editor-canvas`** (or `.react-flow__*`) driven by **`--pipeliner-graph-*`** vars mapped from `tokens.graph.*`. |
| **`<Background />`** | Default dot/grid color | Pass **`color` / `gap` / `size`** from theme (or CSS vars if the component supports them) so the grid matches **`--background`** / canvas token. |
| **Edges** | No `defaultEdgeOptions` in current `ReactFlow` usage | Stroke, animation, and hover should use **graph tokens**, not accidental library light-theme defaults. |
| **Node-type semantics** | Stage (accent rail), pipeline (`--text-secondary` rail), step (success rail), trigger (accent + gradient), target (success + gradient) | Either map to **`tokens.graph.nodeStageRail`**, **`tokens.graph.nodeStepRail`**, etc., **or** document as fixed “diagram language” that does not follow global accent — product choice. |
| **Selection** | `.react-flow__node.selected .pipeline-editor-node` | Already partly themed; ensure **selection ring** colors read against canvas when presets change. |

#### 10.5.4 Non-color coupling (layout contract)

`src/lib/graphTransform.ts` encodes **pixel geometry** (gaps, header heights, trigger row heights) with comments pointing at **`App.css`** selectors. Runtime theme that changes **padding, borders, or font metrics** must **update both** CSS and these constants, or extract shared **spacing tokens** used by both. This is **not** a separate “theme layer” in the admin editor unless we explicitly add **density** tokens later.

#### 10.5.5 Relation to pilot rollout (§10.2)

- If the pilot route is the **pipeline editor** (`/pipelines` or `/pipelines/:id`), **§10.5.3** is in scope for the first **`--pipeliner-graph-*`** batch; **§10.5.2** items on the same page can migrate in the same PR if the diff stays small.
- If the pilot is another route, **§10.5.2** still applies to that route’s components; graph tokens wait until the pipeline editor is opted in.

## 11. Security

- All **mutations** use `require_admin_managed_auth` (same pattern as `app/routes/invitations.py`).
- **`/theme/runtime`:** `require_managed_auth` — any authenticated user sees resolved theme (no PII in payload).
- **Rate limiting / size:** cap `config` JSON size (e.g. 256KB) to avoid abuse.
- **Audit (optional v1):** log admin preset changes with `user_id` and preset id.

## 12. Testing

- **API tests:** admin CRUD + 403 as non-admin; runtime merge with/without active preset; validation 422; system preset delete forbidden.
- **Frontend tests:** gated nav; applyTheme sets variables.
- **Migration test:** local `supabase db reset` applies migration cleanly.

## 13. Rollout

**Phase A — Backend only**

1. Migration: `ui_theme_presets`, `app_ui_theme_settings`, optional seed + RLS as decided in §5.2.
2. `UiThemeService` + repository: merge, validation, `cssVars` map.
3. Routes: `GET /theme/runtime` + full `/management/ui-theme/*` table from §8.
4. API tests from §12.

**Phase B — Admin editor only (still no global theme)**

5. `notion_pipeliner_ui`: API client + **admin Theme page** per §10.1 (nav gated).
6. Editor uses **scoped preview** only; verify CRUD + set active against dev DB.

**Phase C — Single pilot page**

7. Pick **one** route; implement `useRuntimeUiTheme()` + wrapper `div` per §10.2.
8. Convert **only** that page’s styling for **a minimal token set** (keep diff small).
9. QA: regression on **all other routes** (they should be bit-identical to pre-change visually).

**Phase D — Expand (separate tickets per page)**

10. Repeat: one route per ticket, each opt-in to the hook + `var(--pipeliner-*)`.
11. When coverage is sufficient, optional **global shell** application per §10.3.

**Explicit don’ts until Phase D/global:**

- Do not add runtime theme fetch to `App.tsx`, root `ThemeProvider`, or `AppShell` (except the **admin nav link**).
- Do not change shared layout chrome (sidebar, header) to use `--pipeliner-*` until those are included in an explicit ticket (otherwise every page “changes” visually).

## 14. Open decisions (pre-implementation)

- Exact v1 `tokens.*` catalog with design.
- Whether `GET /theme/runtime` must support **unauthenticated** clients for a branded login screen.
- Where the JSON Schema file lives and whether the frontend validates with `ajv` or defers to API-only validation.
- **Supabase client mode:** service role vs user JWT for new tables — drives whether RLS is mandatory on day one.

---

## References

- [require_admin_managed_auth](../../../../app/dependencies.py) — `user_type == "ADMIN"`
- [Phase 5 visual editing index](./index.md)
- [Style / admin theming research](../../../style/admin-theming-design-tokens-research.md)
