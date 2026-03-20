# Architecture: Property Set Step Detail View — Selectable Property

Date: 2026-03-18  
Status: Proposed  
Owner: Product + Platform

## Problem

The Property Set step is the primary way to write values into a data target (e.g., a Notion database). Its most important configuration lives in raw JSON:

```json
{
  "schema_property_id": "prop_source"
}
```

Users must manually type these IDs into the Config (JSON) field. This is error-prone, hard to discover, and inconsistent with the rest of the inspector UX. The Property Set template is fundamentally about **selecting which property on the job's data target to set** — that selection should be driven by UI controls, not raw JSON.

**Data target is job-level.** The job defines `target_id`; pipeline steps inherit it. Steps configure *which property* to set, not which target.

## Goals

- Expose `schema_property_id` and write mode as first-class, selectable controls in the Property Set detail view.
- Use dropdowns/selectors populated from the job target's schema (`GET /management/data-targets/{job.target_id}/schema`).
- Support both schema-property writes and page-metadata writes (icon/cover) through clear UI.
- Keep raw JSON as an advanced escape hatch only.
- Preserve full compatibility with the existing backend config model.

## Non-goals

- Changing the Property Set runtime handler or config contract.
- Supporting cross-target writes (steps always write to the job's target).
- Building a generic config-schema UI renderer; this doc focuses on Property Set specifically.

---

## Current Model

### Property Set Config Schema

From `step_template_property_set.yaml`:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `schema_property_id` | string | — | — | ID of the schema property to set (when `target_kind` = schema_property) |
| `target_kind` | string | — | schema_property | One of: `schema_property`, `page_metadata` |
| `target_field` | string | — | — | When page_metadata: `cover_image` or `icon_image` |

### Two Write Modes

1. **Schema property** — Write to a database column (e.g., Name, Tags, Source).
   - Requires: `schema_property_id`
   - Property options come from `GET /management/data-targets/{job.target_id}/schema`

2. **Page metadata** — Write to page-level icon or cover.
   - Requires: `target_kind: "page_metadata"`, `target_field: "cover_image" | "icon_image"`
   - No schema property selection; fixed field set.

### Existing APIs

| Endpoint | Purpose |
|----------|---------|
| `GET /management/data-targets` | List data targets (id, display_name, status, …) for the owner |
| `GET /management/data-targets/{target_id}/schema` | Fetch properties for a target (id, name, property_type, options, …) |
| `GET /management/step-templates/{template_id}` | Full template metadata including config_schema |

### Pipeline Context

- The job has a `target_id` (the primary data target). Pipeline steps inherit it; they do not configure it.
- Property Set steps configure *which property* on that target to set.
- The inspector has access to job/pipeline context (`target_id`) when rendering the step detail view.

---

## Proposed UI Design

### Configuration Section (Property Set Template)

When the user selects the Property Set template, the **Configuration** section shows:

#### 1. Write mode

**Label:** Write to  
**Control:** Segmented control or radio group  
**Options:**
- **Schema property** (default) — Write to a database column
- **Page metadata** — Write to icon or cover image

**Maps to:** `config.target_kind`

#### 2a. Property selector (when Write mode = Schema property)

**Label:** Property  
**Control:** Searchable dropdown / select  
**Options source:** `GET /management/data-targets/{job.target_id}/schema` → `properties[].{id, name, property_type}`  
**Display:** Show `name` (e.g., "Source", "Tags"); use `id` as value  
**Required:** Yes when schema_property mode  
**Maps to:** `config.schema_property_id`

**Dependency:** Schema is fetched using job `target_id` from pipeline context. No data target selector—steps inherit the job's target.

#### 2b. Metadata field (when Write mode = Page metadata)

**Label:** Field  
**Control:** Select  
**Options:** `cover_image`, `icon_image` (with friendly labels: "Cover image", "Icon image")  
**Required:** Yes when page_metadata mode  
**Maps to:** `config.target_field`

### Field Order

1. Write mode (schema_property vs page_metadata)
2. Property (conditional) or Field (conditional)

### Node Summary Sync

When the user selects a property, the graph node subtitle should update, e.g.:
- Schema property: `"Source"` or `"Tags"`
- Page metadata: `"Cover image"` or `"Icon image"`

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Inspector: Property Set Step Selected                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. Load pipeline context (job.target_id)                                 │
│ 2. GET /management/data-targets/{job.target_id}/schema                   │
│    → populate Property dropdown (when schema_property mode)               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ User selects Write mode (schema_property | page_metadata)                 │
│   → Set config.target_kind                                               │
│   → Show Property selector OR Field selector                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ User selects Property or Field                                           │
│   → Set config.schema_property_id OR config.target_field                  │
│   → Update node subtitle                                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Config Schema Enhancement (Optional)

To make the inspector fully schema-driven, we can extend `config_schema` in the step template with UI hints:

```yaml
config_schema:
  schema_property_id:
    type: string
    ui_control: schema_property_select
    options_source_ref: job.target_id  # GET /management/data-targets/{job.target_id}/schema
  target_kind:
    type: string
    default: schema_property
    ui_control: segmented
    options:
      - { value: schema_property, label: Schema property }
      - { value: page_metadata, label: Page metadata }
  target_field:
    type: string
    ui_control: select
    options:
      - { value: cover_image, label: Cover image }
      - { value: icon_image, label: Icon image }
```

This is optional for a first pass. The frontend can hard-code Property Set–specific rendering and add schema-driven hints later.

---

## Implementation Plan

### Phase 1: Property Set–specific controls (recommended first)

1. **Add Property Set detection in inspector**
   - When `step_template_id === "step_template_property_set"`, render the custom Configuration section instead of generic config_schema fields.

2. **Write mode selector**
   - Radio/segmented: "Schema property" | "Page metadata".
   - Sync to `config.target_kind`. Default `schema_property`.

3. **Property selector**
   - Visible when `target_kind === "schema_property"`.
   - Fetch `GET /management/data-targets/{job.target_id}/schema` using pipeline context.
   - Dropdown: property `name` as label, `id` as value.
   - Disable or show placeholder when no schema / loading.

4. **Field selector**
   - Visible when `target_kind === "page_metadata"`.
   - Fixed options: Cover image, Icon image.
   - Sync to `config.target_field`.

5. **Config sync**
   - All control changes write to `step.config` immediately.
   - Preserve any extra config keys (e.g., future extensions) when merging.
   - Raw JSON in Advanced section still reflects full config; edits there should merge back.

### Phase 2: Schema-driven hints (optional)

1. Extend `config_schema` in step template YAML with `ui_control`, `options_source`, etc.
2. Build a generic config renderer that uses these hints for Property Set and other templates.
3. Fall back to generic string/number/boolean controls for unknown types.

---

## API Contract Summary

No new endpoints required. Existing:

| Endpoint | Used for |
|----------|----------|
| `GET /management/data-targets/{target_id}/schema` | Property dropdown options (use `job.target_id` from pipeline context) |
| `GET /management/step-templates/{template_id}` | Template metadata including config_schema |

### Pipeline payload

The pipeline/job graph must include `target_id` at the job level. The inspector uses this to fetch schema for the Property selector. This is already present in the current model.

---

## Edge Cases

| Case | Behavior |
|------|----------|
| Job has no target_id | Show message "Pipeline has no data target. Set target in pipeline settings." |
| Schema not yet synced | Property dropdown empty or loading; show "Schema not available" or "Sync schema" CTA if applicable |
| Step has invalid config (e.g. schema_property_id references deleted property) | Show current value; mark as invalid; allow user to re-select |
| Page metadata mode | Hide Property selector; show Field selector only |
| Advanced JSON edited | Merge raw JSON into config; form controls reflect merged state; overwrite conflicting keys from form |

---

## Acceptance Criteria

- [ ] When Property Set step is selected, Configuration section shows Write mode and Property/Field selectors (not raw JSON).
- [ ] Data target is inherited from job; no Data target dropdown.
- [ ] Write mode selector: "Schema property" | "Page metadata".
- [ ] When Schema property: Property dropdown is populated from `GET /management/data-targets/{job.target_id}/schema`.
- [ ] Property dropdown shows property name, stores property id.
- [ ] When Page metadata: Field dropdown with Cover image / Icon image.
- [ ] All edits sync to `step.config` immediately; graph node subtitle updates.
- [ ] Raw config JSON remains in Advanced section for power users.
- [ ] Invalid or missing schema_property_id does not block save; validation can surface warnings.

---

## Relationship to p5_proposal-details-view-cleanup

This document is a **drill-down** of the Property Set–specific configuration described in the broader [p5_proposal-details-view-cleanup.md](./p5_proposal-details-view-cleanup.md). That proposal defines:

- Template / Step / Inputs / Configuration / Output / Advanced section layout
- Schema-driven config rendering
- Target-schema-aware field controls

This architecture doc specifies:

- Exact UI for Property Set: write mode, property/field selectors (data target inherited from job)
- Data flow and API usage
- Dependency: schema fetch uses job.target_id

Implementing this doc fulfills the Property Set portion of the broader cleanup proposal.
