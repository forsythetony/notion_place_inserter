# Binding picker: step output surface metadata (labels, summaries, example payloads)

**Status:** Pilot shipped 2026-03-25 (validation + tests + picker); §12 catalog-wide metadata rollout optional follow-up  
**Related:** [Pipeline cell / step detail UI polish](./productization-technical/beta-launch-readiness/pipeline-cell-step-detail-ui-polish.md), [Pipeline step options analysis](./pipeline-step-options-analysis.md)  
**Repositories:** `notion_place_inserter` (catalog YAML, management APIs, optional validation), `notion_pipeliner_ui` (`BindingPickerModal`, `availableSignals`)

## 1. Problem

When a user configures bindings (for example **Cache Set → value** immediately after **Google Places Lookup**), the picker lists **machine-oriented output keys** (`search_response`, `selected_place`) with no explanation of:

- What each blob **represents** in product terms.
- What **shape** they should expect (nested fields, arrays, raw API vs normalized object).
- Which option is **recommended** for typical downstream steps.

Today the editor derives labels solely from `output_contract.fields` keys (`notion_pipeliner_ui/src/lib/availableSignals.ts` → `outputFieldNames`). That is correct for wiring but weak for comprehension.

## 2. Goal

Extend the **step template catalog** so each declared output field can carry **optional, authorable metadata** consumed by the binding picker:

- **Human title** (replaces or augments the raw key in lists).
- **Short summary** (one or two sentences).
- **Illustrative example JSON** — a **small structural sketch** (nesting, array vs object, a few representative keys), not a dump of everything the API can return. The point is to show **shape**, not to teach the full payload or overwhelm the picker.

The same pattern should apply to **any** step template with multiple outputs (AI steps, transforms, external lookups), not only Google Places.

## 3. Non-goals (for this spec)

- **Replacing** `output_contract.fields.<name>.type` or adding strict **runtime** validation from example data.
- **Live** “sample from last run” in the picker (possible follow-up; requires run storage and privacy review).
- **Auto-generating** examples from Google’s OpenAPI in v1 (optional later; v1 is hand-authored in YAML).

## 4. Design principles

1. **Backward compatible:** Templates without new keys behave exactly as today (show `outputNames` as today).
2. **Template-owned:** Copy and examples live with the step definition (YAML catalog), not scattered in frontend strings — keeps product behavior aligned with what the worker actually returns.
3. **Illustrative, not contractual:** UI must label examples as **representative**; Google and our merge logic can add/remove fields. Avoid promising exact keys in user-facing copy unless tied to a versioned schema doc.
4. **Structure-first, minimally noisy:** Examples should be **short** so users see hierarchy and field names at a glance — not walls of JSON they will not read. A hard byte/nesting cap in validation (see §5.2) is a **secondary** guardrail (API payloads, accidental paste); the **primary** constraint is editorial: *only what communicates structure*.

## 5. Proposed config shape (catalog / `output_contract`)

Keep existing:

```yaml
output_contract:
  fields:
    search_response:
      type: object
    selected_place:
      type: object
```

Extend each field with **optional** nested metadata (names are suggestions; finalize in implementation PR):

| Key | Type | Purpose |
|-----|------|---------|
| `title` | string | Primary label in the picker (e.g. “Raw search response”). If omitted, use the field key. |
| `summary` | string | 1–3 sentences shown under the title. |
| `example` | JSON-serializable object | Pretty-printed in UI as “Example shape (illustrative)” — **minimal** tree showing structure; omit rarely used branches. |
| `pick_hint` | string | Optional badge text, e.g. “Usually best for property mapping” / “Advanced / debugging”. |

**Example** (Google Places — illustrative content only; tighten against real API responses when authoring):

```yaml
output_contract:
  fields:
    search_response:
      type: object
      title: Raw text-search payload
      summary: >-
        The structured response from the Places text search call (multiple candidates,
        pagination metadata, etc.). Use when you need the full API envelope or downstream
        steps expect the search response shape—not the single merged place object.
      pick_hint: Advanced — full API envelope
      example:
        places:
          - id: places/ChIJ...
            displayName:
              text: Stone Arch Bridge
            formattedAddress: "100 Portland Ave, Minneapolis..."
        # In production YAML: stop here — enough to show `places[]` + nested shape; do not paste full API samples.
    selected_place:
      type: object
      title: Resolved place (first hit + optional details)
      summary: >-
        The place the runtime selected (first search result), merged with Place Details
        when enabled. Use for typical mappings (name, address, photos, summaries).
      pick_hint: Recommended for most bindings
      example:
        id: places/ChIJ...
        displayName: Stone Arch Bridge
        formattedAddress: "100 Portland Ave, Minneapolis, MN 55401"
        addressComponents: []
        photos: []
```

### 5.1 YAML vs database (authoritative YAML, Postgres mirror, startup reconciliation)

**Authoring source:** `product_model/catalog/step_templates/*.yaml`. Reviewers align copy and illustrative `example` JSON with handler code in the same PR as YAML changes.

**Runtime source of truth for the API:** `step_templates` in Postgres (`PostgresStepTemplateRepository`). The editor reads templates via management routes from this table — not by reading the repo’s YAML on the fly.

**Startup “upgrade” / catalog reconciliation (existing pattern):** On API boot, when `ENABLE_BOOTSTRAP_PROVISIONING` is enabled (default `1`), `PostgresBootstrapProvisioningService.seed_catalog_if_needed()` runs (`app/services/postgres_seed_service.py`). It scans every `product_model/catalog/step_templates/*.yaml`, parses each file with `parse_step_template`, and **`upsert`s the full row** into `step_templates` (including `output_contract` JSON) keyed by template `id`.

That is the intended **upgrade path** for new output metadata:

1. Extend YAML (`title`, `summary`, `example`, etc. under `output_contract.fields.*`).
2. Deploy the API (or restart locally).
3. Startup seed **refreshes** Postgres from YAML so environments that were seeded on an older build **gain the new fields** without a dedicated SQL migration for JSON blobs — as long as bootstrap provisioning runs.

**Operational implications:**

- Treat platform catalog rows as **YAML-owned**: hand-editing `step_templates` in SQL for ids that ship in repo YAML will be **overwritten** on the next successful startup sync. Product copy and examples should be changed in YAML.
- If bootstrap is disabled (`ENABLE_BOOTSTRAP_PROVISIONING=0`), operators must run an equivalent sync job or migration, or Postgres will stay stale relative to YAML.
- The method name is `seed_catalog_if_needed`, but the implementation **always** re-upserts every catalog file it finds (idempotent refresh). Naming could be clarified in a small refactor to `sync_catalog_from_yaml` if that reduces confusion.

**Optional DB-only overrides (second phase, not required for your model):** If we ever need **hotfix** display strings without deploy, introduce an explicit overlay table or column with a documented **merge** rule (e.g. overlay wins for `title`/`summary`/`example` only, YAML supplies defaults). This is separate from startup reconciliation and should be rare if YAML + deploy remains the norm.

### 5.2 Validation (backend / CI)

**Authoring norm (human):** Reviewers reject examples that look like exported API traces. Target **a handful of levels** and **a few keys per object**; use `[]` / `...` in comments in the PR description if needed — the stored `example` should stay a compact skeleton.

On catalog load or in a CI check:

- `title`, `summary`, `pick_hint` are strings under max length (e.g. 200 / 2000 / 80 chars).
- `example` serializes to JSON; enforce a **modest max nesting depth** and optionally a **byte ceiling** per field (e.g. 8–16 KB) as a backstop against accidental huge pastes — not as the main way we keep examples small.
- Warn if a field declares `example` but `type` is not `object`/`array` (still allowed for scalars if ever needed).

No requirement that `example` matches live API responses byte-for-byte.

## 6. API and domain

- **`StepTemplate.output_contract`** already flows through management routes (`app/routes/management.py` returns `output_contract` for inspector/forms). No new top-level property — nesting under `fields` keeps one schema document.
- **Parsing:** `YamlStepTemplateRepository` / `parse_step_template` already materializes `output_contract`; ensure unknown keys inside `fields.<name>` are preserved (if the loader currently strips nested keys, adjust).
- **Frontend types:** `ManagementStepTemplateItem.output_contract` should be typed to allow `fields[name]` as `{ type, title?, summary?, example?, pick_hint? }` rather than only `{ type }`.

## 7. UI changes (`notion_pipeliner_ui`)

### 7.1 Data plumbing

- Extend `PrecedingStepOutputInfo` in `src/lib/availableSignals.ts` from flat `outputNames: string[]` to either:
  - **`outputs: { key: string; title: string; summary?: string; example?: unknown; pickHint?: string }[]`**, or
  - Keep `outputNames` for backward compatibility and add parallel `outputMeta: Map` — prefer a single structured list to avoid drift.

- `outputFieldNames` becomes **`outputsFromTemplate(tmpl)`** returning structured rows; callers that only need keys use `.map(o => o.key)`.

### 7.2 `BindingPickerModal`

Current flow: pick step → list **keys** → optional dot path (`pathSignal`).

Updates:

1. **Output list rows** show `title` (fallback: key), optional `pick_hint` as a small pill, and **first line of `summary`** (truncated).
2. **Detail step:** After choosing an output, before or beside the path input, show a **collapsible** “Example structure (illustrative)” panel with pretty-printed JSON (`JSON.stringify(example, null, 2)`), monospace, modest max-height (examples are expected to be short), optional **Copy** button, and short helper text that this shows **shape** only — not the full runtime object.
3. **Accessibility:** Collapsible region labeled; no information-only tooltips without keyboard access.

### 7.3 Tests

- Extend `availableSignals.test.ts` for templates with enriched `output_contract.fields`.
- Snapshot or assert **BindingPickerModal** renders title + summary snippet when present.

## 8. Paradigm for other templates

Any step with `output_contract.fields` can opt in field-by-field:

- **Optimize Input:** `optimized_query` vs raw metadata (if exposed).
- **AI / constraint steps:** `structured_output` vs debug fields.
- **Cache Get:** outputs are usually passthrough; lower priority unless multiple named exports exist.

Document in each template’s YAML **why** a user would pick each output, not only what the API returned.

## 9. Phased delivery

| Phase | Scope |
|-------|--------|
| **P0** | Schema + loader preservation + management JSON passthrough + picker list rows (title/summary/hint). |
| **P1** | Example JSON panel + copy; CI validation (depth / optional byte backstop); authoring guidance in reviews for **minimal** structural examples. |
| **P2** | Optional DB overlay for copy; optional “link to docs” field. |

## 10. Acceptance criteria (implementation)

- Google Places template ships authored `title`/`summary`/`example` for `search_response` and `selected_place`.
- Templates with no metadata **unchanged** in UI.
- Management API returns full nested `output_contract`; frontend does not strip unknown field properties.
- Documented validation rules enforced where applicable; examples in catalog remain **structural sketches** by convention (oversized examples fail review or CI).
- **Rollout checklist:** Use **§12** as the working list of other `product_model/catalog/step_templates/*.yaml` files that should gain the same contract metadata over time (track in the same PR series or as follow-up tickets).

## 11. Open questions

- Should the picker show **field key** as secondary text (for power users) even when `title` is set? (Recommendation: yes, muted monospace.)
- Do we want **locale** keys later (`title_i18n`) or English-only until beta hardens?

## 12. Rollout deliverable: catalog templates to enrich with output metadata

One **expected output** of this initiative (alongside code and UI) is a **completed pass** over the platform catalog: each template below should eventually get optional `title` / `summary` / structural `example` (and `pick_hint` where useful) on every **`output_contract.fields` entry**, consistent with §5. Treat this section as a **checklist** for implementation and copy review; order is **priority** (user confusion in the binding picker), not file name.

Paths are relative to `product_model/catalog/step_templates/`.

### High priority (multiple outputs or high ambiguity)

- **`step_template_google_places_lookup.yaml`** — Pilot: `search_response` vs `selected_place` (raw search envelope vs resolved place object).
- **`step_template_ai_select_relation.yaml`** — `selected_page_pointer` vs `selected_relation` (Notion pointer object vs relation array; easy to bind the wrong one).

### Medium priority (single output but shape or integration is easy to misunderstand)

- **`step_template_ai_constrain_values_claude.yaml`** — `selected_values` (array / constrained option structure from Claude).
- **`step_template_data_transform.yaml`** — `transformed_value` (shape depends on transform expression / input type).
- **`step_template_templater.yaml`** — `rendered_value` (string result of template interpolation).
- **`step_template_search_icons.yaml`** — `image_url` (Freepik or resolved asset URL).
- **`step_template_upload_image_to_notion.yaml`** — `notion_image_url` (Notion-hosted file URL after upload).
- **`step_template_extract_target_property_options.yaml`** — `options` (enumerated property options from target schema).

### Lower priority (single primitive output; metadata still improves consistency)

- **`step_template_ai_prompt.yaml`** — `value` (plain model text).
- **`step_template_optimize_input_claude.yaml`** — `optimized_query` (string for downstream Places/query steps).
- **`step_template_cache_get.yaml`** — `value` (passthrough blob from run cache; shape is whatever was cached).

### No `output_contract` fields to document (skip for this feature)

- **`step_template_cache_set.yaml`** — `output_contract: {}` (side-effect step; nothing to pick as a prior step output).
- **`step_template_property_set.yaml`** — `output_contract: {}` (terminal write; same).

**Process note:** As each YAML file is updated, keep examples **structural and minimal** (§4, §5.2). The same startup **YAML → Postgres** reconciliation (§5.1) applies so environments pick up new metadata after deploy.
