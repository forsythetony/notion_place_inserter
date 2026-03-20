# Proposal: Pipeline Step Inspector Cleanup and Schema-Driven Details Pane

Date: 2026-03-18  
Status: Proposed  
Owner: Product + Platform

## Why this proposal

The current right-side inspector gets the job done, but it is too text-heavy and too dependent on raw JSON editing for step configuration. That makes the editor feel inconsistent, harder to scan, and harder to trust when building pipelines step by step.

We already have most of the data needed for a much better inspector:

1. Step templates define `input_contract`, `output_contract`, and `config_schema`.
2. Target schema APIs expose property metadata and selectable options.
3. The editor already treats the graph and the inspector as two views over the same pipeline payload.

This proposal redesigns the inspector so that adding a new step immediately opens a cleaner, schema-aware configuration surface with:

1. A template picker at the top.
2. Shared fields rendered consistently across all step types.
3. Template-specific fields rendered below based on the selected step template.
4. Inline previews for upstream input context, schema/property options, and output shape.
5. Immediate local sync between inspector edits and the selected node in the graph.

This is a pragmatic first step toward a richer card-style step picker later. For now, the top-of-inspector template dropdown is sufficient. See [p5_step-template-picker-architecture.md](./p5_step-template-picker-architecture.md) for the architecture proposal defining the command-palette-style picker with card detail and fuzzy search.

## Goals

- Make the step inspector feel clean, consistent, and ergonomic instead of text-heavy.
- Replace raw JSON editing for common step configuration with typed form controls.
- Let users add a step and configure it immediately without leaving the selected node context.
- Make shared vs template-specific fields visually obvious.
- Show helpful context from previous step outputs and target schema metadata while editing.
- Keep graph node state and inspector state in sync instantly in local editor state.
- Preserve compatibility with the current backend graph model and save flow.

## Non-goals

- Building the future card-style step picker in this pass.
- Reworking the entire graph layout system.
- Introducing full autosave to backend on every keystroke.
- Replacing all advanced configuration with custom controls on day one.

## Current state

The current backend/editor contract already supports a strong inspector redesign, but there are a few important constraints.

### What already exists

- `StepTemplate` already contains:
  - `display_name`
  - `description`
  - `category`
  - `input_contract`
  - `output_contract`
  - `config_schema`
- `StepInstance` already cleanly separates:
  - shared instance fields like `display_name`, `step_template_id`, `sequence`, `failure_policy`
  - instance configuration in `config`
  - upstream references in `input_bindings`
- `GET /management/data-targets/{target_id}/schema` already returns property metadata and options, which is exactly what the inspector needs for target-aware pickers.
- Existing step configs already demonstrate the desired UX direction. For example, the bootstrap job includes `step_template_ai_constrain_values_claude` with:
  - previous-step input bound through `signal_ref`
  - allowable values loaded from a target schema property via `target_schema_ref`
  - numeric configuration like max output values

### Current gaps

- The current `/management/step-templates` response is too shallow for schema-driven forms because it returns only summary metadata.
- Validation currently checks structural integrity and some template-specific rules, but it does not generically validate `StepInstance.config` against `StepTemplate.config_schema`.
- New pipeline bootstrap still creates a default `Property Set` step pointed at page metadata, which is not a neutral starting point for a more guided inspector flow.
- The frontend inspector implementation is not present in this checkout, so this proposal is based on the persisted model, API contract, and existing planning docs for the Phase 5 editor.

## Proposed user experience

## 1) Add Step flow

When the user clicks `Add` inside a pipeline:

1. A new step node is inserted into the graph immediately.
2. The new node becomes the selected node.
3. The inspector opens in `Step setup` mode.
4. The first field in the inspector is `Step template`, rendered as a searchable dropdown.

Recommended initial behavior:

- Create a local editor-only draft step with placeholder presentation like `Choose step type`.
- Do not require a real persisted `step_template_id` until the user selects one.
- Block save for any step that is still in draft/unconfigured state.

This supports the desired interaction without forcing the backend to persist an arbitrary default template.

## 2) Inspector layout

Every step inspector should use the same high-level section order:

1. `Template`
2. `Step`
3. `Inputs`
4. `Configuration`
5. `Output`
6. `Advanced`

### Template

Top row:

- `Step template` dropdown
- optional category badge
- short template description under the control

Changing the selected template should:

- update the node title/icon/chrome immediately
- replace the template-specific fields in the inspector
- preserve compatible shared fields where reasonable
- reset or quarantine incompatible config fields
- refresh the output preview

### Step

Shared fields shown for every step:

- `Display name`
- `Sequence` when manual ordering is allowed
- `Failure policy` when applicable

These should use standard text/select controls instead of JSON.

### Inputs

This section should explain where the step gets its input from.

For each expected input from `input_contract`:

- show the current binding source
- show a readable binding label instead of raw JSON
- show preview text when a previous step output is available
- allow binding changes through form controls instead of manual JSON

Examples:

- `Previous step output`
- `Trigger payload`
- `Static value`
- `Target schema property options`
- `Cache value`

For a first pass, the inspector can still keep an `Advanced JSON` escape hatch for uncommon binding shapes, but the default UI should be structured.

### Configuration

This is the main template-specific form area.

Render fields from `config_schema` using consistent controls:

- string -> text input or textarea
- integer/number -> numeric input with min/max where known
- boolean -> toggle
- enum/options -> select, segmented control, chips, or multi-select
- object references -> selector rows with labels and summaries

The section should use field groups with compact helper text and stable spacing so every step feels like it belongs to the same system.

### Output

The inspector should always show a compact output preview derived from the template's `output_contract`.

Examples:

- `AI Prompt` -> `value: string`
- `AI Constrain Values` -> `selected_values: array`
- `Property Set` -> write-only / terminal step

When the output depends on a selected property or target shape, the preview can include a short note such as:

- `Writes to multi_select property: Tags`
- `Reads options from target schema property: Tags`

### Advanced

Keep advanced/raw controls behind a collapsed section:

- raw `input_bindings` JSON
- raw `config` JSON
- low-level IDs or internal references

This preserves power-user flexibility without making the default experience feel unfinished.

## 3) Example: AI constrain values step

This step is the clearest example of why the inspector should be schema-aware.

Desired flow:

1. User adds a step.
2. User selects `AI Constrain Values (Claude)` from the template dropdown.
3. Inspector shows `Input preview` using the previous step output when available.
4. Inspector shows `Property source` picker scoped to the current target schema.
5. User selects `Tags`.
6. Inspector shows a compact list of tag options as chips or a small card list.
7. User sets:
   - `Max allowed values = 3`
   - `Max suggested values = 0`
   - optional prompt/help text for additional guidance
8. Output preview updates to show `selected_values: array`.
9. The selected graph node updates immediately with a clearer summary, such as `Tags, max 3`.

Recommended first-pass form for this template:

- `Input source`
- `Property source`
- `Available values preview`
- `Max allowed values`
- `Max suggested values`
- `Strictness / eagerness`
- `Prompt guidance` if we extend this template to support explicit prompt text

Notes:

- The current template already supports `allowable_values_source`, `max_suggestible_values`, `allowable_value_eagerness`, and `max_output_values`.
- If prompt text is desired for this step, the template contract may need a small extension rather than a pure UI change.

## 4) Node summary behavior

As the user edits the inspector, the graph node should become more informative.

Examples:

- `Property Set` node subtitle could show the selected property name.
- `AI Prompt` node subtitle could show a prompt preview or token cap.
- `AI Constrain Values` node subtitle could show the selected property and max values.

This makes the graph easier to scan without requiring the user to reopen the inspector constantly.

## Shared and template-specific fields

The inspector should make the separation explicit.

### Shared fields

These come from `StepInstance` and should be visually grouped first:

- `display_name`
- `step_template_id`
- `sequence`
- `failure_policy`
- normalized `input_bindings` presentation

### Template-specific fields

These come from `StepTemplate.config_schema` and should be rendered in a separate `Configuration` section.

Examples:

- `Property Set`
  - `schema_property_id`
  - `target_kind`
  - `target_field`
  (Data target is job-level; steps inherit it.)
- `AI Prompt`
  - `prompt`
  - `max_tokens`
- `AI Constrain Values`
  - `allowable_values_source`
  - `max_suggestible_values`
  - `allowable_value_eagerness`
  - `max_output_values`

## Data and API updates

## 1) Step template metadata for the inspector

Current endpoint:

- `GET /management/step-templates`

Current problem:

- returns only summary metadata

Proposal:

Either expand the existing response or add a detail endpoint so the inspector can load:

- `input_contract`
- `output_contract`
- `config_schema`
- optional field-level labels, help text, defaults, and control hints

Recommended contract addition:

- `GET /management/step-templates/{template_id}`

If performance is acceptable, returning the richer shape from the list endpoint is even simpler for the editor.

## 2) Field metadata normalization

Today, `config_schema` is usable but still minimal. To support clean forms consistently, we should allow optional metadata such as:

- `label`
- `description`
- `required`
- `default`
- `ui_control`
- `placeholder`
- `min`
- `max`
- `options_source`

This can stay backward compatible by treating existing schema fields as the minimum supported form.

## 3) Validation improvements

The backend should eventually validate:

- required config fields based on selected `StepTemplate.config_schema`
- data types for simple config values
- allowed binding shapes for fields defined by `input_contract`

This is important because once the UI becomes more structured, validation should reinforce the same contracts instead of relying mostly on editor correctness.

## 4) Draft step handling

Because the persisted model expects a real `step_template_id`, draft steps should remain editor-local until configured.

Save behavior:

- if any draft step remains unresolved, disable save or return a clear client-side validation message
- only serialize fully configured steps into the canonical graph payload

This keeps the backend model clean while still supporting the desired add-first, choose-template-second interaction.

## Inspector sync model

The sync model should stay simple and predictable:

1. Inspector edits update the selected node's local editor state immediately.
2. The graph node re-renders immediately from that local state.
3. Graph-to-payload transforms continue to derive the save payload from the current editor state.
4. Explicit save sends the full payload through the existing `PUT /management/pipelines/{id}` flow.
5. The editor replaces local state with the canonical saved response.

This matches the current architecture better than backend autosave on every field edit.

If autosave is explored later, it should be added as a thin layer on top of this local sync model, likely with debounce and optimistic save state.

## Implementation plan

1. **Define inspector form model**
   - Create a frontend-friendly metadata shape for shared fields, input bindings, template config fields, and output preview.
   - Decide which fields use fully custom UI vs schema-driven defaults.

2. **Upgrade step template API**
   - Expose full template metadata needed for schema-driven rendering.
   - Add optional field metadata where current schemas are too thin.

3. **Introduce draft-step editor state**
   - Support local unconfigured steps created by `Add Step`.
   - Prevent invalid saves while a draft step has no selected template.

4. **Replace raw JSON-default inspector**
   - Build shared `Step`, `Inputs`, `Configuration`, and `Output` inspector sections.
   - Keep raw JSON under collapsed `Advanced`.

5. **Add target-schema-aware field controls**
   - Use target schema API for property pickers and options previews.
   - Add compact chips/list previews for select-like properties.

6. **Add node summary sync**
   - Update node subtitle/summary from selected config values so the graph becomes more scannable.

7. **Harden validation**
   - Add client-side validation for required template fields.
   - Add backend validation against template schema as a follow-up where practical.

## Acceptance criteria

- Clicking `Add Step` inserts a new node and immediately opens its inspector.
- The top of the inspector contains a step-template dropdown.
- Selecting a template updates the inspector fields and node presentation immediately.
- Shared fields are shown consistently across all step types.
- Common template-specific fields are edited through typed controls, not raw JSON.
- AI-constrain-values style steps can select a target schema property and show available values in a readable preview.
- The inspector shows a compact output preview for the selected template.
- Editing fields in the inspector updates the selected graph node immediately in local editor state.
- Save continues to work through the existing full-payload editor flow.
- Unsupported or advanced fields remain available under a collapsed advanced section.

## Risks and mitigations

- **Template metadata is not rich enough for polished forms.**  
  Mitigation: add optional UI metadata incrementally while keeping schema-driven fallbacks.

- **Draft step state diverges from persisted graph assumptions.**  
  Mitigation: keep draft steps editor-local and require template resolution before save.

- **Inspector implementation becomes overly custom per template.**  
  Mitigation: establish one shared scaffold and only specialize where the default schema-driven controls are not good enough.

- **The frontend code lives outside this repo.**  
  Mitigation: treat this document as the product/technical contract, then implement against the frontend repo with the API/model constraints documented here.

## Open questions

- Should `Add Step` create a fully local draft node, or should it create a persisted default step that must be changed immediately?
- Do we want to expand `step_template_ai_constrain_values_claude` to support explicit prompt text, or should prompt guidance remain a separate AI step for now?
- Should output preview be purely contract-based, or should we also show sample data snippets from upstream values when available?
- Should `sequence` remain user-editable in the inspector, or be managed only by graph ordering controls?
