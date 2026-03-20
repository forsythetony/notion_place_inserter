# Architecture: Schema-Aware Optimize Input — Query Structure from Downstream Steps

Date: 2026-03-19  
Status: Proposed  
Owner: Product + Platform

## Problem

The `OptimizeInputClaudeHandler` currently optimizes input blindly. It uses a hardcoded prompt in `ClaudeService.rewrite_place_query()` that assumes the downstream consumer is **Google Places**:

> "You are a search query optimizer. Rewrite the user's place search into a concise, effective Google Places text query."

This causes two issues:

1. **Wrong optimization for different consumers** — When Optimize Input feeds **Search Icons** (Freepik), the ideal output is a short 1–3 word visual keyword (e.g. "bridge", "landmark"), not a full place query like "Stone Arch Bridge Minneapolis MN". The current handler produces a Google Places–style query regardless of downstream step.

2. **Config is ignored** — The step template already defines `linked_step_id` and `include_target_query_schema` in `config_schema`, and the bootstrap job configures them (e.g. `linked_step_id: step_google_places_lookup`, `include_target_query_schema: true`), but the handler never uses them.

## Goals

- **Schema-aware optimization** — Optimize Input uses the query structure exposed by the downstream step it feeds.
- **Declarative query schema** — Any step that reaches out to an API can declare the query structure it expects.
- **Backward compatible** — When no linked step or schema is provided, fall back to current behavior (generic Google Places–style optimization).
- **Extensible** — New API-consuming steps (e.g. future Notion search, other providers) can expose their query schema without changing Optimize Input logic.

## Non-goals

- Changing the Optimize Input step template's config contract (`linked_step_id`, `include_target_query_schema` remain for override/edge cases).
- Supporting multiple linked steps (one target consumer per Optimize Input step).

---

## Design: Query Schema from Downstream Steps

### 0. Link Discovery from Pipeline Graph (Primary)

**The link is inferred from the pipeline structure.** When the user adds an Optimize Input step and wires its `optimized_query` output to another step's `query` input, that connection is already visible in the graph. The system uses it automatically — no extra config required.

**Discovery logic:**

1. In the current pipeline, find all steps whose `input_bindings` include a `signal_ref` of the form `step.{this_step_id}.optimized_query`.
2. The first such step is the **linked consumer**. Use its template's `query_schema` for optimization.
3. If multiple steps consume the output (rare), use the first in pipeline order, or allow `linked_step_id` override.

**UI implication:** When the user adds Optimize Input and connects it to the next step (e.g. Google Places Lookup or Search Icons), the link is established by the wiring. The inspector can show "Optimizing for: Google Places Lookup" based on the graph — no dropdown or manual `linked_step_id` needed. Schema-aware optimization happens automatically.

**Optional override:** `linked_step_id` in config can still override auto-discovery when the graph is ambiguous or the user wants to target a specific consumer.

### 1. Step Templates Expose Query Schema

Any step template that consumes a query and calls an external API can declare a **query schema** in its YAML. This describes the shape and expectations of the query for that API.

**Schema shape (proposed):**

```yaml
# In step_template_google_places_lookup.yaml
query_schema:
  api: google_places
  type: string
  description: "Text query for Google Places searchText API (textQuery field)"
  hints:
    - "Include place name and location when known (e.g. 'Stone Arch Bridge Minneapolis MN')"
    - "Avoid conversational or question-style phrasing"
    - "Prefer format: Place Name City Region"
```

```yaml
# In step_template_search_icons.yaml
query_schema:
  api: freepik_icons
  type: string
  description: "Short keyword for Freepik icon search"
  hints:
    - "1-3 words only"
    - "Visual or conceptual term (e.g. bridge, landmark, travel)"
    - "Avoid location names; focus on what the place represents"
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `api` | string | No | Identifier for the target API (for logging, future extensions) |
| `type` | string | No | `string` (default) or future `object` for structured queries |
| `description` | string | Yes | Human-readable description of what the API expects |
| `hints` | list[string] | No | Optimization hints to inject into the LLM prompt |

### 2. Optimize Input Resolves the Linked Step

**Resolution order:**

1. **Config override** — If `linked_step_id` is set in config, use that step (must be in the same pipeline).
2. **Auto-discovery** — Otherwise, scan the pipeline for steps whose `input_bindings` reference `step.{this_step_id}.optimized_query`. Use the first consumer found.
3. **Schema lookup** — Get the linked step's `step_template_id`, load its `query_schema` from the catalog.
4. **Inject** — When `query_schema` exists and `include_target_query_schema` is not explicitly `false`, inject it into the Claude prompt.

**Resolution rules:**

- Linked step must be in the same pipeline as the Optimize Input step.
- If the linked step's template has no `query_schema`, fall back to generic optimization.
- If no linked step can be resolved (no consumers, invalid config), fall back to generic optimization and log a warning.
- `include_target_query_schema: false` disables schema injection even when a linked step exists (opt-out for edge cases).

### 3. Claude Service: Schema-Aware Rewrite

Introduce a new method (or extend the existing one) that accepts optional schema context:

```python
def rewrite_query_for_target(
    self,
    raw_query: str,
    *,
    query_schema: dict[str, Any] | None = None,
    base_prompt: str | None = None,
) -> str:
    """
    Rewrite raw input into an optimized query for a specific target API.
    When query_schema is provided, injects description and hints into the prompt.
    """
```

**Prompt construction when schema is present:**

```
System: You are a search query optimizer. Rewrite the user's input into a query
optimized for the target API.

Target API: {query_schema.description}

Optimization hints:
{query_schema.hints, one per line}

Return only the query string, no explanation.
```

**Prompt when schema is absent:** Use current `rewrite_place_query` behavior (Google Places default).

### 4. Step Template Catalog Access at Runtime

The Optimize Input handler needs access to step template definitions. Options:

| Option | Pros | Cons |
|--------|------|------|
| **A. Inject StepTemplateRepository into JobExecutionService** | Clean dependency; handler receives repo via ctx | Requires new service in execution context |
| **B. Enrich snapshot with step template metadata** | Snapshot is self-contained; no new service | Snapshot grows; resolution step must preload templates for all steps in job |
| **C. Handler receives template catalog in snapshot** | Snapshot already has job structure; add `step_templates` key | Snapshot assembly must fetch templates |

**Recommendation: Option B or C.** Enrich the snapshot during `resolve_for_run` (or at execution start) with `step_templates: { template_id: template_dict }` for all templates referenced by steps in the job. This keeps the handler simple and avoids adding a repository to the execution context.

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Pipeline (from snapshot)                                                    │
│  - step_optimize_query outputs optimized_query                               │
│  - step_google_places_lookup has input_bindings.query:                        │
│      signal_ref: step.step_optimize_query.optimized_query                     │
│  → Link is visible from the graph; no config required                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  OptimizeInputClaudeHandler.execute()                                        │
│  1. linked_step_id from config? OR auto-discover: find step that consumes     │
│     step.{this_step_id}.optimized_query → step_google_places_lookup           │
│  2. step.step_template_id → step_template_google_places_lookup               │
│  3. snapshot["step_templates"][template_id].query_schema → schema            │
│  4. claude.rewrite_query_for_target(query, query_schema=schema)               │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ClaudeService.rewrite_query_for_target()                                   │
│  - Build prompt with schema.description + schema.hints                        │
│  - Return optimized query string                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Step Template Query Schema

1. **Add `query_schema` to step templates** that consume queries:
   - `step_template_google_places_lookup.yaml`
   - `step_template_search_icons.yaml`

2. **Extend catalog schema** (if validated) to allow optional `query_schema` at the template level.

### Phase 2: Snapshot Enrichment

3. **Enrich snapshot with step templates** — When `JobDefinitionService.resolve_for_run` builds the snapshot, collect all `step_template_id` values from the job graph and fetch their full definitions. Add `step_templates: { id: template_dict }` to the snapshot.

4. **Alternative (simpler):** Pass `StepTemplateRepository` (or equivalent) to `JobExecutionService` and use it in the handler. The handler would call `repo.get_by_id(template_id)` when resolving `linked_step_id`. This avoids snapshot changes but adds a dependency.

### Phase 3: Claude Service Extension

5. **Add `rewrite_query_for_target`** to `ClaudeService`:
   - Accept `raw_query`, `query_schema`, optional `base_prompt`
   - When `query_schema` is present, build schema-aware prompt
   - When absent, delegate to existing `rewrite_place_query` logic (or inline equivalent)

### Phase 4: Optimize Input Handler

6. **Implement link discovery and schema resolution in `OptimizeInputClaudeHandler`**:
   - **Link discovery:** If `config.linked_step_id` is set, use it. Otherwise, scan the current pipeline's steps for any whose `input_bindings` reference `step.{step_id}.optimized_query` (where `step_id` is this step's id). Use the first consumer.
   - **Schema lookup:** Get the linked step's `step_template_id`, fetch `query_schema` from snapshot or repository.
   - **Opt-out:** If `config.include_target_query_schema` is explicitly `false`, skip schema injection.
   - Call `claude.rewrite_query_for_target(query, query_schema=schema)` when schema is available; otherwise `rewrite_place_query(query)`.
   - Use `config.prompt` as override for base prompt when provided.

7. **Handler derives pipeline from snapshot** — The handler receives `snapshot` (with `job.stages[].pipelines[].steps`) and `step_id`. Traverse the job graph to find the pipeline that contains this step, then scan that pipeline's steps for consumers of `step.{step_id}.optimized_query`.

### Phase 5: Tests and Documentation

8. **Unit tests** — Optimize Input handler with mocked Claude, schema present vs absent, invalid linked_step_id.
9. **Update `pipeline-step-options-analysis.md`** — Document `query_schema` for Google Places and Search Icons; clarify that `linked_step_id` and `include_target_query_schema` are now implemented.

---

## Example Configurations

### Research Pipeline (Google Places)

The link is established by the wiring: `step_google_places_lookup` consumes `step.step_optimize_query.optimized_query`. No config needed.

```yaml
- id: step_optimize_query
  step_template_id: step_template_optimize_input_claude
  input_bindings:
    query:
      signal_ref: trigger.payload.raw_input
  config: {}   # linked_step_id optional; auto-discovered from graph
- id: step_google_places_lookup
  step_template_id: step_template_google_places_lookup
  input_bindings:
    query:
      signal_ref: step.step_optimize_query.optimized_query
```

**Result:** "stone arch bridge in minneapolis" → "Stone Arch Bridge Minneapolis MN"

### Icon Pipeline (Freepik)

Same pattern: `step_icon_search` consumes `step.step_icon_optimize_query.optimized_query`. Schema-aware optimization happens automatically.

```yaml
- id: step_icon_optimize_query
  step_template_id: step_template_optimize_input_claude
  input_bindings:
    query:
      signal_ref: step.step_google_places_lookup.selected_place.displayName
  config: {}
- id: step_icon_search
  step_template_id: step_template_search_icons
  input_bindings:
    query:
      signal_ref: step.step_icon_optimize_query.optimized_query
```

**Result:** "Stone Arch Bridge" → "bridge" (or "landmark", "architecture" — short visual keyword)

---

## Migration and Backward Compatibility

- **Wired pipelines** — When Optimize Input's output is connected to a downstream step, schema-aware optimization is used automatically. No config changes needed.
- **Unwired or ambiguous** — When no consumer is found (output not connected) or multiple consumers exist, falls back to generic optimization. `linked_step_id` can override to disambiguate.
- **Opt-out** — `include_target_query_schema: false` disables schema injection even when a linked step exists.
- **Step templates** without `query_schema` cause fallback to generic behavior when linked.
- **Invalid `linked_step_id`** (e.g. step in different pipeline, typo) logs a warning and falls back to generic optimization.

---

## Future Extensions

- **Structured query schema** — For APIs that accept more than a single string (e.g. filters, facets), extend `query_schema.type` to `object` with a JSON schema fragment.
- **Multi-consumer** — If one Optimize Input step feeds multiple consumers (e.g. via a fan-out), we could support `linked_step_ids: []` and merge schemas or pick the first. Defer until needed.
- **Schema versioning** — If API providers change their expectations, `query_schema` could include a version field for future evolution.
