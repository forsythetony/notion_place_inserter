# Data and Context Contracts

## Purpose

Define the shared data model used by pipelines, including context keys, property payload assembly, and dry-run output semantics.

## PipelineRunContext Contract

`PipelineRunContext` (`app/pipeline_lib/context.py`) is the shared mutable state for one pipeline run.

Core capabilities:

- Generic key-value exchange: `get(key)`, `set(key, value)`.
- Property payload mutation: `set_property(name, value)`.
- Provenance tracking:
  - `PROPERTY_SOURCES`: property -> resolving pipeline id.
  - `PROPERTY_SKIPS`: property -> skipping pipeline id.
- Snapshot support for debugging/prompt construction: `snapshot()`.

## Context Key Conventions

`ContextKeys` currently defines:

- `RUN_ID`
- `RAW_QUERY`
- `REWRITTEN_QUERY`
- `GOOGLE_PLACE`
- `SCHEMA`
- `PROPERTIES`
- `PROPERTY_SOURCES`
- `PROPERTY_SKIPS`
- `COVER_IMAGE`
- `ICON`

Additional internal keys are also set by services/orchestration (for example `_notion_service`, `_global_pipeline_id`, `_current_pipeline_id`) and should be treated as framework-private.

## Data Handoff Across Stages

### Stage 1 Research

Produces:

- Refreshed `SCHEMA` (`DatabaseSchema`).
- Rewritten query and Google place cache (`GOOGLE_PLACE`).

### Stage 2 Property Resolution

Consumes:

- `SCHEMA` and `GOOGLE_PLACE`.

Produces:

- Incremental `PROPERTIES` dictionary (Notion payload format).
- Optional provenance entries in `PROPERTY_SOURCES` and `PROPERTY_SKIPS`.

### Stage 3 Image Resolution

Consumes:

- `GOOGLE_PLACE`.

Produces:

- `ICON` and `COVER_IMAGE` payloads when resolved.

## Payload Assembly

`PlacesService.create_place_from_query()`:

1. Creates `PipelineRunContext` with injected services and initial `RAW_QUERY`.
2. Executes `places_global_pipeline`.
3. Reads:
   - `context.get_properties()`
   - `context.get_property_sources()`
   - `context.get_property_skips()`
   - `ContextKeys.ICON`
   - `ContextKeys.COVER_IMAGE`
4. Delegates to `create_place(...)` for dry-run response or Notion page creation.

## Property Value Format

Property pipelines and formatting steps write Notion API-compatible shapes, such as:

- `{"title": [...]}`
- `{"rich_text": [...]}`
- `{"select": {"name": "..."} }`
- `{"multi_select": [{"name": "..."}]}`
- `{"url": "https://..."}`
- `{"relation": [{"id": "..."}]}`

This keeps route and service layers format-agnostic.

## Dry-Run Contract

When `DRY_RUN` is enabled, `PlacesService.create_place(...)` does not call Notion page creation.

Instead it returns:

- `mode: "dry_run"`
- `database`
- `properties`
- `summary` (`property_count`, `property_names`)
- optional `keywords`, `icon`, and `cover`

The same property resolution path runs, so dry-run output reflects real inference and formatting behavior.

## Contract Stability Guidelines

- Prefer extending `ContextKeys` over introducing ad-hoc string keys.
- Keep private context keys prefixed with `_` to avoid collisions.
- Any new pipeline output that affects page creation should have an explicit key contract and consumer.
- Preserve Notion payload compatibility at the edge (`NotionService.create_page`).
