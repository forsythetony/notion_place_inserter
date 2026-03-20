# Architecture: Input Binding & Signal Picker — Alternatives to Manual JSON

Date: 2026-03-19  
Status: Proposed  
Owner: Product + Platform

## Decided

- **Picker UX:** Modal picker (Variant B) — "Select source" button opens a modal with categorized list (Trigger, Steps, Cache, Static). User drills down.
- **Cache Get deprecation:** Deprecate the `cache_get` pipeline step. All cache access uses `cache_key_ref` selected via the picker. No more "add cache_get step, wire to its output" pattern. Inputs and config values both use the same picker; under the hood they resolve the same way (`signal_ref`, `cache_key_ref`, `static_value`, `target_schema_ref`).
- **Data flow model (implemented):** **`signal_ref` to `step.*` is pipeline-local only** — a step may reference only preceding steps in the **same** pipeline (and `trigger.*`). **Cross-pipeline or cross-stage data** must use **`cache_set` + `cache_key_ref`** (cache keys are job-wide). Validation enforces this. **`cache_key_ref`** may include an optional **`path`** (dot-separated segments, numeric segments for list indices, e.g. `displayName`, `photos.0.name`) to read a nested field from the cached object without an extra transform step.

---

## Problem

The current step detail view requires users to manually type or paste JSON bindings into input fields, e.g.:

```json
{"signal_ref": "step.step_google_places_lookup.selected_place.displayName"}
```

or for cache:

```json
{"cache_key_ref": {"cache_key": "google_places_response"}}
```

This is error-prone, hard to discover, and inconsistent with the rest of the inspector UX. Users must know the exact syntax, step IDs, output names, and cache keys.

Two design directions have been considered:

1. **Disallow direct cache references** — Require explicit `cache_get` pipeline steps before any step that needs cached data; wire inputs to `cache_get.value`.
2. **Inline signal/cache picker** — Keep the binding model but add a UI picker in the cell detail view so users can select from available signals and cache keys without typing JSON.

This document analyzes when each approach works, identifies collision scenarios, and presents options.

---

## Current Model

### Binding Types

| Binding Type | Description | Example |
|--------------|-------------|---------|
| `signal_ref` | Reference trigger payload or another step's output | `trigger.payload.raw_input`, `step.step_id.output_name` |
| `cache_key_ref` | Reference a value stored in run-scoped cache (optional `path` for nested fields) | `{"cache_key": "google_places_selected_place", "path": "displayName"}` |
| `static_value` | Literal value | `{"static_value": "Notion Place Inserter"}` |
| `target_schema_ref` | Reference target schema metadata (e.g. property options) | `{"schema_property_id": "prop_tags", "field": "options"}` |

### Where Bindings Appear

1. **`input_bindings`** — Steps with `input_contract` receive data via `input_bindings`. Each field (e.g. `value`, `query`, `source_value`) maps to a binding.
2. **Config with bindings** — Some steps have config that accepts bindings:
   - **Templater** — `config.values` is a dict of placeholder key → binding. Each value can be `signal_ref`, `cache_key_ref`, or `static_value`.
   - **AI Constrain Values** — `config.allowable_values_source` can contain `target_schema_ref`.

### Cache Access (Current vs. New Model)

**Legacy pattern (deprecated):** Cache Set → Cache Get step → downstream uses `signal_ref: step.step_cache_get.value`.

**New model:** Cache Set stores; downstream uses `cache_key_ref` in the binding (selected via picker). No `cache_get` step. The picker lists cache keys from all `cache_set` steps in the job; user selects one; binding resolver reads directly from `ctx.run_cache`.

---

## Option 1: Cache Get Only (Disallow cache_key_ref)

### Idea

Disallow `cache_key_ref` in bindings. If a step needs data from cache, the user must add a `cache_get` pipeline step right before the consumer and wire the consumer's input to `cache_get.value`.

### When It Works

| Scenario | Works? | Notes |
|----------|--------|-------|
| Step with single input from cache | ✅ | Add cache_get, wire `input_bindings.value` to `step_cache_get.value`. |
| Step with multiple inputs, some from cache | ✅ | Add one cache_get per cache key needed; wire each input to its cache_get. |
| Step with mixed sources (signal + cache) | ✅ | Wire signal_ref for one input, cache_get for the other. |
| Property Set, Data Transform, AI Prompt, etc. | ✅ | All have input_contract; can wire to cache_get. |

### When It Fails (Collision Scenarios)

| Scenario | Fails? | Reason |
|----------|--------|--------|
| **Templater** | ❌ | Templater has `input_contract: {}` — no inputs. All data comes from `config.values`, a dynamic dict of key → binding. You cannot wire a cache_get to Templater because it has no input fields. The only way to get cache data into Templater is via `cache_key_ref` in `config.values`. |
| **Any step with config-based bindings** | ❌ | If a step gets data from config (not input_bindings) and that config accepts bindings, cache_key_ref is the only way to pull from cache. There is no "input" to wire a cache_get to. |
| **Parallel pipelines** | ⚠️ | If two pipelines run in parallel and one needs data from the other, cache is the only cross-pipeline channel. Cache get would work (add cache_get in the consumer pipeline), but the cache_set must run first. Stage ordering handles this. |

**Conclusion:** Option 1 works for all steps with `input_bindings`. It **fails for Templater** and any future step that uses config-based bindings without an input_contract.

### Mitigation for Templater

To make "cache get only" work for Templater, we would need to:

1. **Add an input_contract to Templater** — But Templater's `values` keys are user-defined (e.g. `latitude`, `longitude`, `name`). We cannot define a fixed input_contract that covers all possible keys.
2. **Support "optional inputs"** — Allow Templater to accept input_bindings that override or supplement config.values when present. E.g. if `input_bindings` has `latitude`, use that; otherwise use `config.values.latitude`. This adds complexity and a new pattern.
3. **Split Templater** — Create a "Templater with inputs" variant that requires all values to be wired. Breaking change for existing jobs.

All mitigations are non-trivial. **Recommendation:** Do not pursue "cache get only" as a universal rule; it breaks Templater without significant refactoring.

---

## Option 2: Inline Signal/Cache Picker (Recommended)

### Idea

Keep `signal_ref` and `cache_key_ref` in the binding model. Add a **picker UI** in the cell detail view so users select from available signals and cache keys instead of typing JSON. The picker generates the correct binding.

### Benefits

- Single, consistent UX for all binding-capable fields.
- Works for both `input_bindings` and config-based bindings (Templater).
- Simpler pipelines — no cache_get steps; cache access via picker + `cache_key_ref`.
- Users see what's available (step outputs, trigger paths, cache keys) instead of guessing.

### Picker Data Sources

The picker needs job/pipeline context to know what's available:

| Source | How to derive | Example options |
|--------|---------------|-----------------|
| **Trigger** | From job's `trigger_id` and known payload shape | `trigger.payload.raw_input` |
| **Step outputs** | From all steps that precede the current step (in pipeline order, including prior stages) | `step.step_google_places_lookup.selected_place`, `step.step_optimize_query.optimized_query` |
| **Cache keys** | From all `cache_set` steps in the job (their `config.cache_key`) | `google_places_response`, `google_places_selected_place` |
| **Static** | Always available | User enters literal value |

### UI Variants

| Variant | Description | Pros | Cons |
|---------|-------------|------|------|
| **A. Inline dropdown** | Each input field shows a dropdown/combobox. User selects "From step output" → picks step → picks output (and optional path). | Compact, no modal. | Can be crowded for nested paths. |
| **B. Modal picker** ✓ | "Select source" button opens a modal with categorized list (Trigger, Steps, Cache, Static). User drills down. | Clear hierarchy, room for preview. | Extra click, context switch. |
| **C. Inline expandable** | Field shows current binding summary (e.g. "step_google_places_lookup.selected_place"). Click to expand picker inline. | Best of both — compact when set, expandable when editing. | Slightly more complex to implement. |

**Chosen:** Variant B — modal picker. When editing a binding-capable field, user clicks "Select source" (or similar); a modal opens with categorized options. Field displays a readable summary when a binding is set (e.g. "step_google_places_lookup.selected_place" or "cache: google_places_response").

### Picker Behavior for Nested Paths

Some bindings need nested paths, e.g. `step.step_google_places_lookup.selected_place.displayName`. Options:

1. **Two-level picker** — First select step + output; then optionally add path (e.g. `.displayName`, `.formattedAddress`). Path could be a second dropdown (from output schema) or a text field for power users.
2. **Path builder** — After selecting base (step output or cache key), show a path builder (add segment, choose key from schema when available).
3. **Hybrid** — Common paths (e.g. `selected_place.displayName`) as quick picks; "Custom path" for advanced.

### Seamless Combination with Existing Inputs

A step can have:
- **Primary input** — e.g. Property Set's `value` from the previous step (signal_ref).
- **Additional sources** — e.g. Templater's `values` with multiple keys, each from a different source.

The picker applies to **each** binding-capable field. So:
- Property Set's `value` → one picker.
- Templater's `values.latitude` → one picker; `values.longitude` → another.

No collision: each field gets its own picker. The user can mix signal_ref, cache_key_ref, and static_value per field.

---

## Option 3: Hybrid — Cache Get for Inputs, Picker for Config

### Idea

- For **input_bindings**: Disallow `cache_key_ref`; require cache_get. Use a **signal picker** (trigger + step outputs only) for wiring. Cache keys never appear in input_bindings.
- For **config bindings** (Templater values): Allow `cache_key_ref` and provide a **full picker** (signals + cache keys) because config cannot be wired.

### Pros

- Inputs are "pipeline-pure" — all data flows through steps.
- Config stays flexible for steps that need it.

### Cons

- Two different mental models: "inputs come from steps" vs "config can come from anywhere."
- Templater would still need cache_key_ref in config; we'd need a picker there anyway. So we're building a picker regardless. The only difference is whether input_bindings can use cache_key_ref.

**Recommendation:** Not worth the complexity. Option 2 (full picker everywhere) is simpler and more consistent.

---

## Option 4: Unified Picker with Optional Auto-Insert Cache Get

### Idea

Always use the picker. When the user selects a cache key for an **input_binding** (not config), the system could optionally offer: "Add a Cache Get step before this step?" If the user accepts, insert the step and use `signal_ref`; if they decline, use `cache_key_ref` directly.

**Decision:** Rejected. We deprecate cache_get entirely. Picker always produces `cache_key_ref` for cache access; no pipeline step.

---

## Summary: Recommended Approach

| Option | Verdict |
|--------|---------|
| **Option 1: Cache get only** | ❌ Fails for Templater; would require non-trivial refactoring. |
| **Option 2: Inline signal/cache picker** | ✅ **Recommended.** Single UX, works for all binding-capable fields, no pipeline changes. |
| **Option 3: Hybrid** | ⚠️ Two mental models; picker needed for config anyway. |
| **Option 4: Picker + optional cache get** | ❌ Rejected; cache_get deprecated. |

**Recommendation:** Implement **Option 2 — Signal/Cache Picker** (modal UX).

1. Add a binding picker component to the step detail view.
2. Use it for all fields that accept bindings: `input_bindings` and config-based bindings (e.g. Templater `values`).
3. Picker sources: Trigger, Step outputs (preceding steps), Cache keys (from cache_set steps in job), Static.
4. **Modal picker UX:** "Select source" opens modal with categorized list; field shows readable summary when set.
5. Support nested paths for step outputs (e.g. `.displayName`, `.formattedAddress`).
6. **Deprecate cache_get step:** Remove from template picker; migrate existing jobs to use `cache_key_ref` via picker instead of `signal_ref` to cache_get output.

---

## Implementation Considerations

### API for Picker Data

The frontend needs a list of available signals and cache keys. Options:

| Approach | Description |
|----------|-------------|
| **A. Derive from job payload** | The editor already has the full job/pipeline. Traverse stages and pipelines to collect: (1) trigger payload paths (from trigger schema or convention), (2) step outputs (from step_template_id → output_contract), (3) cache keys (from cache_set steps' config.cache_key). No new API. |
| **B. New endpoint** | `GET /management/jobs/{job_id}/available-signals` returns structured list. Backend does the traversal. Cleaner separation; frontend stays dumb. |

**Recommendation:** Start with A (derive from job payload). The editor has the graph; step templates are fetched for output_contract. Cache keys come from cache_set steps. Add B later if the derivation logic becomes complex or needs to live server-side.

### Cache Get Deprecation and Migration

| Action | Description |
|--------|-------------|
| **Template catalog** | Mark `step_template_cache_get` as deprecated (e.g. `status: deprecated` or `visibility: hidden`). Exclude from step template picker so new pipelines cannot add it. |
| **Runtime** | Keep `CacheGetHandler` working for existing jobs. Jobs that already use cache_get steps continue to run. No breaking change to execution. |
| **Bootstrap job migration** | Convert bootstrap job pipelines that use cache_get to use `cache_key_ref` instead. E.g. `pipeline_tags` currently has `step_cache_get_places` → `step_constrain_tags` (source_value from cache_get.value). Replace with `step_constrain_tags` having `source_value: {cache_key_ref: {cache_key: "google_places_response"}}` and remove the cache_get step. Same for `pipeline_location`, `pipeline_cover_image`. |
| **Future removal** | After migration and a deprecation period, remove `step_template_cache_get` from the catalog and `CacheGetHandler` from the registry. |

### Output Contract and Path Hints

Step templates define `output_contract` with `fields`. For nested paths (e.g. `selected_place.displayName`), we could:
- Extend output_contract with optional `field_schema` or `example_shape` for path hints.
- Or infer from usage: the bootstrap job already uses paths like `selected_place.displayName`; we could document common paths in the template or discover from run logs.

For v1, allow free-form path entry after base selection; improve with schema hints later.

---

## Relationship to Other Docs

- **[p5_step-detail-section-visual-hierarchy.md](./p5_step-detail-section-visual-hierarchy.md)** — INPUTS is a primary section. The picker is the control that replaces raw JSON in that section.
- **[p5_proposal-details-view-cleanup.md](./p5_proposal-details-view-cleanup.md)** — Defines Inputs section content. This doc specifies *how* input bindings are edited (picker vs. raw JSON).
- **[p5_property-set-detail-view-architecture.md](./p5_property-set-detail-view-architecture.md)** — Property Set has Configuration (property selector) and Inputs (value binding). The picker applies to the value input.
- **[docs/pipeline-step-options-analysis.md](../../../pipeline-step-options-analysis.md)** — Documents binding types and step contracts. This doc builds on that for UX.

---

## Acceptance Criteria

- [ ] Step detail view INPUTS section uses a binding picker instead of raw JSON for fields that accept bindings.
- [ ] **Modal picker:** "Select source" button opens a modal with categorized list (Trigger, Steps, Cache, Static).
- [ ] Picker shows: Trigger paths, Step outputs (from preceding steps), Cache keys (from cache_set steps in job), Static value.
- [ ] When a binding is set, display a readable summary (e.g. "step_google_places_lookup.selected_place" or "cache: google_places_response").
- [ ] Picker supports nested paths for step outputs (e.g. `.displayName`).
- [ ] Templater `config.values` uses the same picker for each value entry.
- [ ] Raw JSON remains in Advanced section for power users.
- [ ] Picker works for both input_bindings and config-based bindings.
- [ ] **Cache get deprecation:** `step_template_cache_get` excluded from template picker; bootstrap job migrated to `cache_key_ref`; existing jobs with cache_get steps continue to run.
