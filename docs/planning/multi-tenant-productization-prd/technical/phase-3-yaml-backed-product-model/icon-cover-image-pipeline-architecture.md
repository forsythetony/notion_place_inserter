# Architecture: Icon and Cover Image Pipelines

## Goal

Define a reusable, YAML-backed pipeline architecture for setting Notion page cover and icon images while running in the same `stage_property_setting` stage that already sets normal properties.

## Requirements

1. Build as reusable components (step templates + configurable step instances).
2. Run icon/cover pipelines in the same stage as property-setting pipelines.
3. Keep terminal write behavior explicit and consistent with existing `Property Set`.
4. Preserve run-scoped cache usage and snapshot-based execution semantics.

## Proposed Reusable Components

### Existing components reused

- `Cache Get`
- `Optimize Input` (named in-product as Optimize query where configured)
- `Property Set`

### New components to add

1. `Data Transform`
   - Purpose: small deterministic transform over step input.
   - Typical operation for cover: extract a single URL from array/object payload.
   - Suggested config:
     - `operation` (e.g. `extract_key`, `first_non_empty`, `json_path`)
     - `source_path` (e.g. `photos[0].url`)
     - `fallback_value` (optional)
   - Output: `transformed_value`

2. `Upload Image to Notion`
   - Purpose: ingest external image URL and return Notion-hosted URL usable for page metadata writes.
   - Suggested config:
     - `connector_instance_id` (Notion-capable connector)
     - `source_type` (`external_url` in V1)
     - `timeout_ms` (optional)
   - Input: one image URL string.
   - Output: `notion_image_url`

3. `Search Icons` (if not already present)
   - Purpose: search icon source from optimized query.
   - Suggested config:
     - `connector_instance_id`
     - `provider` (e.g. icon service)
     - `result_preference` (e.g. `light_theme`, `flat`, `outline`)
   - Input: optimized query string.
   - Output: `image_url`

## Property Set Extension for Metadata Targets

Keep `Property Set` as the terminal writer, but allow configurable target scope:

- `target_kind: schema_property` (existing behavior)
- `target_kind: page_metadata` (new behavior)

For `page_metadata`, allowed `target_field` values in V1:

- `cover_image`
- `icon_image`

This preserves one reusable terminal write primitive while making icon/cover explicit and typed.

## Pipeline Designs

## Cover image pipeline

1. `Cache Get` (exists)
   - Input: none
   - Output: array/object of location images from Google Place cache
2. `Data Transform` (new)
   - Input: array/object of location images
   - Output: single image URL
   - Operation: deterministic key/path extraction
3. `Upload Image to Notion` (new)
   - Input: single image URL
   - Output: Notion URL
4. `Property Set` (exists, extended target mode)
   - Input: Notion URL string
   - Output: none
   - Config: `target_kind: page_metadata`, `target_field: cover_image`

## Icon pipeline

1. `Optimize Input` (exists; configured as Optimize query)
   - Input: pointer to cache value (Google Places payload or selected subset)
   - Output: structured optimized query
   - Config:
     - `include_target_query_schema` (read schema from downstream step when enabled)
     - `prompt` (custom instruction)
     - `input_signal_refs`/cache pointer for source content
2. `Search Icons` (new or existing if already implemented)
   - Input: optimized query
   - Output: image URL
3. `Upload Image to Notion` (new)
   - Input: single image URL
   - Output: Notion URL
4. `Property Set` (exists, extended target mode)
   - Input: Notion URL string
   - Output: none
   - Config: `target_kind: page_metadata`, `target_field: icon_image`

## Stage Placement and Execution

Place both pipelines inside existing `stage_property_setting` alongside ordinary property pipelines (`tags`, `notes`, `source`, etc).

- Stage execution remains sequential at the job level.
- Pipelines inside `stage_property_setting` remain parallel by default.
- Each icon/cover pipeline still terminates in `Property Set`, preserving existing validation rule shape.

Recommended behavior for metadata collisions in the same stage:

- last successful `Property Set` write for a given metadata field wins (`cover_image` and `icon_image` treated independently).

## Suggested YAML Shape (illustrative)

```yaml
stages:
  - id: stage_property_setting
    pipeline_run_mode: parallel
    pipelines:
      - id: pipeline_cover_image
        steps:
          - id: step_cover_cache_get
            step_template_id: step_template_cache_get
          - id: step_cover_extract_url
            step_template_id: step_template_data_transform
          - id: step_cover_upload_notion
            step_template_id: step_template_upload_image_to_notion
          - id: step_cover_property_set
            step_template_id: step_template_property_set
            config:
              target_kind: page_metadata
              target_field: cover_image

      - id: pipeline_icon_image
        steps:
          - id: step_icon_optimize_query
            step_template_id: step_template_optimize_input_claude
          - id: step_icon_search
            step_template_id: step_template_search_icons
          - id: step_icon_upload_notion
            step_template_id: step_template_upload_image_to_notion
          - id: step_icon_property_set
            step_template_id: step_template_property_set
            config:
              target_kind: page_metadata
              target_field: icon_image
```

## Validation Rules

Add/extend save-time and execution-time validation:

1. `Property Set` with `target_kind: page_metadata` must use supported `target_field`.
2. `Upload Image to Notion` input must resolve to non-empty URL string.
3. `Data Transform` must declare a deterministic operation and source path.
4. `Search Icons` output must normalize to one URL.
5. Existing terminal-step rule remains unchanged (`Cache Set` or `Property Set`).

## Observability

Track per-step run summaries for debugging:

- `Data Transform`: selected path + output length (not full payload)
- `Upload Image to Notion`: source host + upload result status + returned URL domain
- `Property Set`: `target_kind`, `target_field`, write status

This makes icon/cover troubleshooting comparable to existing property write diagnostics.

## Rollout Plan

1. Add new step templates (`Data Transform`, `Upload Image to Notion`, `Search Icons`).
2. Extend `Property Set` config schema for `page_metadata` targets.
3. Update bootstrap job YAML with `pipeline_cover_image` and `pipeline_icon_image` inside `stage_property_setting`.
4. Add unit/integration tests for:
   - validation and binding
   - successful metadata writes
   - error handling (invalid URL, upload failure, empty transform output)
5. Run manual validation against live Notion target.
