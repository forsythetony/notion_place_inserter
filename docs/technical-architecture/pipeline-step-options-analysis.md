# Pipeline Step Options — Detailed Analysis

This document provides a comprehensive analysis of all pipeline step templates available in the Notion Place Inserter system. For each step, it describes inputs, outputs, configuration options, and runtime behavior.

---

## Overview

| Step Template ID | Display Name | Category | Terminal? |
|------------------|--------------|----------|-----------|
| `step_template_optimize_input_claude` | Optimize Input (Claude) | transform | No |
| `step_template_google_places_lookup` | Google Places Lookup | lookup | No |
| `step_template_cache_set` | Cache Set | utility | **Yes** |
| `step_template_cache_get` | Cache Get *(deprecated)* | utility | No |
| `step_template_ai_constrain_values_claude` | AI Constrain Values (Claude) | transform | No |
| `step_template_property_set` | Property Set | output | **Yes** |
| `step_template_data_transform` | Data Transform | transform | No |
| `step_template_templater` | Templater | transform | No |
| `step_template_search_icons` | Search Icons | transform | No |
| `step_template_upload_image_to_notion` | Upload Image to Notion | output | No |
| `step_template_ai_select_relation` | AI Select Relation | transform | No |
| `step_template_ai_prompt` | AI Prompt | ai | No |
| `step_template_extract_target_property_options` | Extract Target Property Options | utility | No (metadata only) |

**Terminal steps:** A pipeline must end with either `cache_set` or `property_set`. These steps produce no downstream outputs.

---

## Input Binding Types

Steps receive inputs via **input bindings** that resolve at runtime. Supported binding types:

| Binding Type | Description | Example |
|---------------|-------------|---------|
| `signal_ref` | Reference trigger payload or another step's output | `trigger.payload.raw_input`, `step.step_id.output_name` |
| `cache_key_ref` | Reference a value stored in run-scoped cache; optional `path` (dot notation) traverses nested fields on the cached value | `{"cache_key": "google_places_response"}` or `{"cache_key": "google_places_selected_place", "path": "displayName"}` |
| `static_value` | Literal value | `{"static_value": "Notion Place Inserter"}` |
| `target_schema_ref` | Reference target schema metadata (e.g. property options) | `{"schema_property_id": "prop_tags", "field": "options"}` |

---

## 1. Optimize Input (Claude)

**Template ID:** `step_template_optimize_input_claude`  
**Step Kind:** `optimize_input`  
**Handler:** `OptimizeInputClaudeHandler`

### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Raw input text to be rewritten into an optimized search query |

### Output

| Field | Type | Description |
|-------|------|-------------|
| `optimized_query` | string | Claude-rewritten query optimized for the downstream consumer. Falls back to original query if Claude service is unavailable or input is empty. |

### Configuration

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `prompt` | string | No | — | Custom prompt override for Claude (appended with input when schema-aware) |
| `linked_step_id` | string | No | — | Override: step ID to use for schema lookup (must be in same pipeline). When omitted, auto-discovered from pipeline graph. |
| `include_target_query_schema` | boolean | No | `true` | When `false`, disables schema injection even when a linked step exists. |

### Runtime Behavior

- **Schema-aware optimization:** When the step's `optimized_query` output is wired to another step's `query` input, the handler auto-discovers that consumer and uses its template's `query_schema` (description + hints) to tailor the Claude prompt. No config required when the pipeline is wired.
- **Fallback:** When no linked step or no `query_schema` exists, uses generic Google Places–style optimization.
- If Claude service is unavailable, returns the original query (stripped).
- Records LLM token usage when `usage_accounting` service is available.

---

## 2. Google Places Lookup

**Template ID:** `step_template_google_places_lookup`  
**Step Kind:** `google_places_lookup`  
**Handler:** `GooglePlacesLookupHandler`

### Query Schema

This template exposes a `query_schema` for schema-aware Optimize Input:

| Field | Value |
|-------|-------|
| `api` | `google_places` |
| `description` | Text query for Google Places searchText API (textQuery field) |
| `hints` | Include place name and location when known; avoid conversational phrasing; prefer format: Place Name City Region |

### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Search query (typically from Optimize Input or trigger) |

### Output

| Field | Type | Description |
|-------|------|-------------|
| `search_response` | object | Raw Google Places API search response, or the first place object if raw response is empty |
| `selected_place` | object | First result from search, optionally enriched with details (generativeSummary, editorialSummary, addressComponents, neighborhood, photos) |

### Configuration

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `connector_instance_id` | string | No | — | Connector instance for Google Places API (used for service resolution) |
| `fetch_details_if_needed` | boolean | No | `true` | If true, fetches place details when the first result lacks summary or address data |

### Runtime Behavior

- Calls Google Places API to search for places.
- If `fetch_details_if_needed` is true and the first result lacks `generativeSummary`/`editorialSummary`, fetches place details by `place_id`.
- Records external API usage for `search_places` and optionally `get_place_details`.

---

## 3. Cache Set

**Template ID:** `step_template_cache_set`  
**Step Kind:** `cache_set`  
**Handler:** `CacheSetHandler`  
**Terminal:** Yes

### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `value` | any | No | Value to store in run-scoped cache |

### Output

Empty object `{}` — terminal step; no downstream outputs.

### Configuration

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `cache_key` | string | **Yes** | — | Key under which to store the value in `ctx.run_cache` |

### Runtime Behavior

- Writes `value` to `ctx.run_cache[cache_key]`.
- If `cache_key` is missing, no write occurs.
- Cache is scoped to the current job run; values persist only for the duration of that run.

---

## 4. Cache Get

**Template ID:** `step_template_cache_get`  
**Step Kind:** `cache_get`  
**Handler:** `CacheGetHandler`  
**Status:** **Deprecated** — Use `cache_key_ref` in bindings (selected via the signal/cache picker) instead of adding a cache_get step. See [p5_input-binding-signal-picker-architecture.md](productization-technical/phase-5-visual-editing/p5_input-binding-signal-picker-architecture.md).

### Input

None. This step has no input contract.

### Output

| Field | Type | Description |
|-------|------|-------------|
| `value` | any | Value retrieved from cache, or `None` if key is missing or invalid |

### Configuration

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `cache_key` | string | **Yes** | — | Key to read from `ctx.run_cache` |

### Runtime Behavior

- Reads `ctx.run_cache.get(cache_key)`.
- Returns `None` if the key does not exist.

---

## 5. AI Constrain Values (Claude)

**Template ID:** `step_template_ai_constrain_values_claude`  
**Step Kind:** `ai_constrain_values`  
**Handler:** `AiConstrainValuesClaudeHandler`

### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_value` | any | No | Context for AI selection (e.g. place data, search response). Passed to Claude as candidate context. |

### Output

| Field | Type | Description |
|-------|------|-------------|
| `selected_values` | array | List of selected option names (strings). May be truncated by `max_output_values`. |

### Configuration

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `allowable_values_source` | object | No | — | Source of allowed options. Must contain `target_schema_ref` with `schema_property_id` and optional `field` (default `"options"`). |
| `max_suggestible_values` | integer | No | — | Max number of values the AI may suggest that are not in the allowed list (used with `allowable_value_eagerness`) |
| `allowable_value_eagerness` | integer | No | `0` | If > 0, enables suggestion behavior: AI may propose new values not in the options list |
| `max_output_values` | integer | No | — | If set, truncates `selected_values` to this length |
| `model` | string | No | — | Model override (schema only; handler uses default Claude) |

### `allowable_values_source` Structure

```yaml
allowable_values_source:
  target_schema_ref:
    schema_property_id: prop_tags   # ID of the target schema property
    field: options                  # Optional; defaults to "options"
```

Options are resolved from the job's active schema (target database) at runtime.

### Runtime Behavior

- Resolves options via `target_schema_ref` from `active_schema.properties[].options`.
- Passes `source_value` to Claude as candidate context (dict, list, or scalar).
- Uses `claude.choose_multi_select_from_context()` to select from options; may suggest new values if `allowable_value_eagerness` > 0.
- Truncates output to `max_output_values` if configured.
- **Failure semantics:** If the Claude service is not configured on the execution context, or the Anthropic API call fails, the step returns a **structured failed** `StepExecutionResult` (orchestrator persists `error_detail` with `service`, `operation`, `retryable`, etc.). It does **not** silently return empty `selected_values` in those cases. Use `failure_policy: continue_with_default` on the step if the pipeline should proceed with default outputs (`selected_values: []`).
- **Observability:** Processing logs follow input summary → configuration summary → `[StepRuntime]` calling service → `[ClaudeService]` LLM request/response + token usage (when trace is available) → output summary. Live-test manual overrides skip the API but still log input/output summaries where applicable.

---

## 6. Property Set

**Template ID:** `step_template_property_set`  
**Step Kind:** `property_set`  
**Handler:** `PropertySetHandler`  
**Terminal:** Yes

### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `value` | any | No | Value to write to the target property or page metadata |

### Output

Empty object `{}` — terminal step; no downstream outputs.

### Configuration

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `schema_property_id` | string | No* | — | ID of the target schema property to write. Required when `target_kind` is `schema_property`. |
| `target_kind` | string | No | `schema_property` | Either `schema_property` (write to a property) or `page_metadata` (write icon/cover). |
| `target_field` | string | No | — | Required when `target_kind` is `page_metadata`. Must be `cover_image` or `icon_image`. |

\* Validation requires `schema_property_id` for `schema_property` and `target_field` for `page_metadata`.

### Runtime Behavior

- **schema_property:** Calls `ctx.set_property(schema_property_id, value)` to queue the property write.
- **page_metadata:** Converts `value` to a Notion icon/cover payload and sets `ctx.cover` or `ctx.icon`. Accepts:
  - Dict with `type` in `external`, `file`, `file_upload`
  - Dict with `external.url`
  - String URL starting with `http://` or `https://`

Allowed `target_field` values: `cover_image`, `icon_image`.

---

## 7. Data Transform

**Template ID:** `step_template_data_transform`  
**Step Kind:** `data_transform`  
**Handler:** `DataTransformHandler`

### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `value` | any | No | Input object or value to traverse |

### Output

| Field | Type | Description |
|-------|------|-------------|
| `transformed_value` | any | Value returned by the JMESPath `expression`, or `fallback_value` if the expression yields no result |

### Configuration

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `expression` | string | No | `""` | JMESPath expression, e.g. `photos[0].name`, `[0]`, `[*].firstProp` |
| `fallback_value` | any | No | — | Value returned when path does not exist |

### Expression Syntax

- `formattedAddress` — object field lookup
- `photos[0].name` — nested field and array indexing
- `[0]` — first element of the input array
- `[*].firstProp` — project one field from every object in the input array

### Runtime Behavior

- Evaluates `expression` against `value` with JMESPath.
- Returns `fallback_value` if the expression yields `None`, is empty, or is invalid.

---

## 8. Templater

**Template ID:** `step_template_templater`  
**Step Kind:** `templater`  
**Handler:** `TemplaterHandler`

### Input

None. Values come from the `values` config object.

### Output

| Field | Type | Description |
|-------|------|-------------|
| `rendered_value` | string | String with `{{key}}` placeholders replaced by resolved values |

### Configuration

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `template` | string | **Yes** | — | Template string with `{{key}}` placeholders |
| `values` | object | No | `{}` | Map of placeholder key → binding. Each value can be `static_value`, `cache_key_ref`, `signal_ref`, or a literal. |

### `values` Binding Examples

```yaml
values:
  name:
    signal_ref: step.step_google_places_lookup.selected_place.displayName
  cached:
    cache_key_ref:
      cache_key: google_places_response
  literal:
    static_value: "Hello"
```

### Runtime Behavior

- Resolves each value in `values` via `resolve_binding()`.
- Replaces `{{key}}` in the template with the string representation of the resolved value.
- Missing keys become empty string.
- Non-scalar values are converted with `str()`.

---

## 9. Search Icons

**Template ID:** `step_template_search_icons`
**Step Kind:** `search_icons`
**Handler:** `SearchIconsHandler`

### Query Schema

This template exposes a `query_schema` for schema-aware Optimize Input:

| Field | Value |
|-------|-------|
| `api` | `freepik_icons` |
| `description` | Short keyword for Freepik icon search |
| `hints` | 1-3 words only; visual or conceptual term (e.g. bridge, landmark, travel); avoid location names |

### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Search term for icon lookup |

### Output

| Field | Type | Description |
|-------|------|-------------|
| `image_url` | string | URL of the first icon result from Freepik, or `None` if service unavailable |

### Configuration

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `connector_instance_id` | string | No | — | Connector instance for Freepik (used for service resolution) |
| `provider` | string | No | — | Provider override (schema only) |
| `result_preference` | string | No | — | Result preference (schema only) |

### Runtime Behavior

- Uses Freepik service to search icons by query.
- Returns the first icon URL via `freepik.get_first_icon_url()`.
- Returns `None` if Freepik service is unavailable.

---

## 10. Upload Image to Notion

**Template ID:** `step_template_upload_image_to_notion`  
**Step Kind:** `upload_image_to_notion`  
**Handler:** `UploadImageToNotionHandler`

### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `value` | string | Yes | Image URL (http/https) or Google Places photo resource name (e.g. `places/.../photos/...`) |

### Output

| Field | Type | Description |
|-------|------|-------------|
| `notion_image_url` | any | Notion icon/cover payload (`{type: "external", external: {url: "..."}}` or file upload), or `None` on failure |

### Configuration

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `connector_instance_id` | string | No | — | Connector instance for Notion (used for OAuth token resolution) |
| `source_type` | string | No | `external_url` | Source type (schema only; handler infers from value format) |
| `timeout_ms` | integer | No | `15000` | Timeout in ms for fetching external URLs (clamped 1000–60000) |

### Runtime Behavior

- **External URL:** Fetches image bytes (max 5MB), uploads via Notion API, returns file upload payload.
- **Google photo name:** Uses Google Places service to get photo bytes, uploads to Notion.
- **Dry-run mode:** Does not upload; returns external URL payload for http/https URLs, or resolves Google photo to external URL.
- **Already Notion payload:** If `value` is a dict with `type` in `external`, `file`, `file_upload`, passes through.
- Uses owner's OAuth token when available; falls back to global token with a warning.

---

## 11. AI Select Relation

**Template ID:** `step_template_ai_select_relation`  
**Step Kind:** `ai_select_relation`  
**Handler:** `AiSelectRelationHandler`

### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_value` | any | No | Primary context for AI matching (e.g. address string, place data) |
| `value` | any | No | Fallback if `source_value` is missing; both are used as context |

### Output

| Field | Type | Description |
|-------|------|-------------|
| `selected_page_pointer` | object | `{id: "<page_id>"}` or `None` |
| `selected_relation` | array | `[{id: "<page_id>"}]` for Notion relation format, or `[]` |

### Configuration

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `related_db` | string | **Yes** | — | Target ID (e.g. `target_locations`) — the related Notion database to query |
| `key_lookup` | string | No | `title` | Property name to use for matching. Supports `title`, `rich_text`, `select`, and case-insensitive aliases. |
| `prompt` | string | No | — | Custom prompt for Claude to choose the best matching page |

### Runtime Behavior

- Resolves `related_db` to a Notion data source ID via `targets` in snapshot (by `display_name` or `external_target_id`).
- Queries the Notion database for pages, extracting the `key_lookup` value from each (title, rich_text, or select).
- Passes candidates and `source_value`/`value` context to Claude.
- Uses `claude.choose_best_relation_from_candidates()` to pick the best match.
- Returns the selected page ID in both `selected_page_pointer` and `selected_relation` formats for downstream Property Set (relation type).

---

## 12. AI Prompt

**Template ID:** `step_template_ai_prompt`  
**Step Kind:** `ai_prompt`  
**Handler:** `AiPromptHandler`

### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `value` | any | No | Input to pass to the prompt. Use `{{value}}` or `{{input}}` in the prompt; otherwise input may be appended. |

### Output

| Field | Type | Description |
|-------|------|-------------|
| `value` | string | Model's text response |

### Configuration

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `prompt` | string | **Yes** | — | The prompt text. Placeholders: `{{value}}`, `{{input}}`. |
| `max_tokens` | integer | No | `1024` | Maximum tokens for the model response |

### Runtime Behavior

- Calls `claude.prompt_completion(prompt, value, max_tokens)`.
- Records LLM token usage when `usage_accounting` is available.
- Returns empty string if prompt is missing or Claude is unavailable.

---

## 13. Extract Target Property Options

**Template ID:** `step_template_extract_target_property_options`  
**Step Kind:** `extract_target_property_options`  
**Handler:** None (metadata/schema only)

### Input

None.

### Output

| Field | Type | Description |
|-------|------|-------------|
| `options` | array | Option list for the target property (resolved via schema) |

### Configuration

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `schema_property_id` | string | **Yes** | — | ID of the target schema property whose options to extract |

### Runtime Behavior

- **No runtime handler.** This step is used for schema/metadata and UI (e.g. property picker, option resolution).
- Options are resolved via `target_schema_ref` in other steps (e.g. AI Constrain Values) that reference the same `schema_property_id`.

---

## Reference: File Locations

| Resource | Path |
|----------|------|
| Step templates (YAML) | `product_model/catalog/step_templates/step_template_*.yaml` |
| Step handlers | `app/services/job_execution/handlers/*.py` |
| Step registry | `app/services/job_execution/job_execution_service.py` |
| Binding resolver | `app/services/job_execution/binding_resolver.py` |
| Validation (terminal rules) | `app/services/validation_service.py` |
| Bootstrap job example | `product_model/bootstrap/jobs/notion_place_inserter.yaml` |

---

## Reference: Management API

- `GET /management/step-templates` — List all templates with `input_contract`, `output_contract`, `config_schema`
- `GET /management/step-templates/{template_id}` — Full template metadata for inspector forms
