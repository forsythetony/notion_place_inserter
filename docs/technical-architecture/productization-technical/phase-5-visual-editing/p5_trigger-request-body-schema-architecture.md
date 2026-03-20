# Architecture: Trigger request body schema (flat, typed, UI-guarded)

Date: 2026-03-19  
Status: Proposed  
Owner: Product + Platform

## Problem

HTTP triggers (e.g. `POST /triggers/{user_id}/locations`) accept a JSON body, but today the contract is split across layers:

- **Runtime** — The locations route uses a hardcoded Pydantic model (`keywords` only) and builds `trigger_payload` as `{"raw_input": <keywords>}` for execution and binding resolution (`trigger.payload.raw_input`).
- **Datastore** — `trigger_definitions.request_body_schema` already exists (`jsonb`), but shapes are inconsistent: bootstrap YAML may use full JSON Schema, while `POST /management/triggers` seeds a flat map `{"keywords": "string"}`.
- **Authoring** — In the visual editor, authors cannot see a single source of truth for “what fields does this trigger expose?” when wiring `signal_ref` bindings or reading the graph.

We need one **canonical, flat, typed schema** per trigger, **strict creation/editing guard rails** (no arbitrary JSON Schema editing in v1), and **visibility in both the trigger inspector and the trigger node** in the graph.

## Goals

1. **Associate schemas with triggers** — Each trigger has a declarative description of POST body fields (flat object: field name → type metadata).
2. **V1 types** — Only `string` and `number` in the authoring UI and validation surface; the design must allow **new types later** (boolean, enum, nested object, arrays, formats, etc.) without rewriting storage.
3. **Hard guard rails** — Schema changes happen through a **structured editor** (add/remove/rename rows, pick type from an allowlist). No hand-edited JSON for end users in v1.
4. **Graph + inspector UX** — Selecting the trigger shows the schema in the detail pane **and** a compact **table-like preview on the trigger node** so authors see fields at a glance while editing the graph.
5. **Runtime alignment** — Validate incoming POST bodies against the stored schema and produce a **trigger payload shape that matches field names**, so bindings can use predictable paths (e.g. `trigger.payload.keywords` instead of ad hoc `raw_input`), subject to a defined migration path (see below).

## Non-goals (v1)

- Arbitrary JSON Schema authoring (allOf, $ref, composition, conditionals).
- Nested objects or arrays in the body schema (explicitly deferred; see **Extensibility**).
- Non-HTTP trigger types.
- Public OpenAPI generation (may reuse the same canonical model later).

---

## Current anchors in the repo

| Layer | Today |
|--------|--------|
| DB | `trigger_definitions.request_body_schema` (`jsonb`, default `{}`) — see Phase 4 migration. |
| Domain | `TriggerDefinition.request_body_schema: dict[str, Any]` — permissive. |
| Invoke | `app/routes/locations.py` — fixed `TriggerLocationsRequest`, `keywords` → `trigger_payload.raw_input`. |
| Bindings | `binding_resolver.py` — `trigger.payload.raw_input` convention. |
| Management create | `POST /management/triggers` — sets `request_body_schema={"keywords": "string"}`. |

---

## Canonical model

### Design principles

- **Storage is JSON-serializable** — Suitable for `jsonb`, YAML export, and future “download schema as `.json`.”
- **Version field** — Top-level `schema_version` (integer) so we can evolve the envelope without ambiguous inference.
- **Field map** — Ordered display can use declared `field_order: string[]`; if omitted, UI sorts keys lexicographically for stability.
- **Per-field spec** — Each field has a `type` taken from a **closed set** at validation time; extra keys are ignored in v1 but reserved for future metadata (`description`, `format`, `enum`, `default`, constraints).

### Recommended JSON shape (v1)

```json
{
  "schema_version": 1,
  "field_order": ["keywords"],
  "fields": {
    "keywords": { "type": "string" },
    "limit": { "type": "number" }
  }
}
```

**Legacy normalization (ingest only):**

- Flat map `{"keywords": "string"}` → treat as `schema_version: 1` with `fields.keywords.type = "string"`.
- JSON Schema blob (`type: object`, `properties`) → one-time migration transforms to v1 `fields` where each property maps to `type` only if it is `string` or `number`; anything else is flagged for manual review or rejected.

### Type registry (extensibility)

Define a server-side and UI-shared **allowlist**:

| `type` value | V1 supported | Future |
|----------------|---------------|--------|
| `string` | Yes | add `min_length`, `max_length`, `pattern`, `format` |
| `number` | Yes | add `integer` distinction, min/max |
| `boolean` | No (reserved) | v2 |
| `enum` | No (reserved) | v2 |

Unknown `type` values in stored data:

- **Authoring:** surface as read-only with “unsupported type — upgrade app” or block save until migrated.
- **Runtime:** fail closed (422) or treat as opaque string (product decision); default recommendation is **422 with clear error**.

---

## Validation rules (v1)

### Field names

- Non-empty string keys; match a safe key pattern (e.g. `^[a-zA-Z_][a-zA-Z0-9_]*$`) to avoid JSON Pointer ambiguity and dotted-path bugs in `signal_ref`.
- **At least one field** — Triggers that accept a body should have ≥1 field for v1 HTTP POST (product may allow empty for webhook ping; if so, document exception).

### Types

- **string:** JSON string at runtime.
- **number:** JSON number at runtime (reject numeric strings unless product explicitly coerces — default **no coercion** for predictability).

### Unknown body keys

- **Recommendation:** Reject with 422 (“unknown field `foo`”) when schema is non-empty, so the contract stays strict. Optionally allow ` additionalProperties: false` explicitly in the canonical model later.

---

## API & services

### Management (authoring)

- **GET** trigger (existing) — Include normalized `request_body_schema` in the payload used by the editor.
- **PATCH** trigger (or **PUT** graph with embedded trigger) — Accept only the structured schema DTO; run **canonical validation** before persist:
  - Reject invalid keys, unknown types (for current server version), duplicate field names, empty field names.
  - Strip or ignore unknown top-level keys on field specs.

### Invocation (runtime)

- Load trigger by path + owner; read `request_body_schema`.
- **Parse body as JSON object.**
- Validate against normalized v1 rules; on failure → **400/422** with field-level errors.
- Build **`trigger_payload`** as the **validated flat object** (same keys as schema), e.g. `{"keywords": "…", "limit": 12}`, not `raw_input`, for new triggers.

### Snapshot / worker

- Job snapshot already carries trigger metadata where applicable; ensure resolved snapshot includes **`request_body_schema`** (or hash) so historical runs remain explainable. Worker consumes `trigger_payload` from queue — no schema re-validation required if API already validated (optional defensive check in worker is acceptable).

---

## UI architecture (`notion_pipeliner_ui`)

### Structured schema editor (guard rails)

- **No Monaco/raw JSON** for typical users.
- **Table or key-value list:** columns **Field name**, **Type** (select: String / Number only in v1), optional **Actions** (remove row).
- **Add field** — Appends a row with default type `string`; inline validation on name (pattern, uniqueness).
- **Rename field** — If bindings reference `trigger.payload.old_name`, show blocking warning or offer automated rebinding (future); v1 may **disallow rename** once trigger is linked to jobs with bindings (product choice).

### Trigger node (graph)

- Custom React Flow node for the pipeline’s **trigger**:
  - **Header:** display name + path (or iconography per style guide).
  - **Body:** **mini-table** — one row per field: **name** · **type** (badge).
  - **Overflow:** if &gt; N rows, show first N + “+k more” to preserve node size; full list remains in inspector.
- **Read-only on canvas** in v1 (editing in inspector only) to avoid accidental edits; optional double-click to focus inspector later.

### Trigger inspector (cell detail)

- Same data as node preview, plus room for **constraints** when types gain them later.
- Link to **“Copy field path”** for bindings: e.g. `trigger.payload.keywords` — aligns with [p5_input-binding-signal-picker-architecture.md](./p5_input-binding-signal-picker-architecture.md) and reduces picker drift.

### Signal picker integration

- **Trigger** section lists one entry per schema field (not only `raw_input`).
- Implementation detail: derive **available signals** from normalized `fields` + naming convention `trigger.payload.<field>`.

---

## Migration: `raw_input` → named fields

Today many graphs bind **`trigger.payload.raw_input`**. Changing payload shape is breaking.

**Phased approach:**

1. **Dual-read period (recommended):** When the schema exposes a `keywords` field, the API may accept `{"keywords": "..."}` and still populate `trigger_payload` with both `keywords` and `raw_input` (duplicate) for one release, with deprecation warning in logs/docs.
2. **Snapshot-time migration:** When opening/saving a pipeline, offer or auto-rewrite bindings from `trigger.payload.raw_input` → `trigger.payload.keywords` when the schema declares `keywords`.
3. **Remove `raw_input`:** After telemetry shows no legacy bindings, stop emitting `raw_input`.

**Implemented (2026-03-19):** Schema-driven validation and `trigger_payload` in `app/services/trigger_request_body.py`; save-time binding migration resolves `trigger.payload.raw_input` → `trigger.payload.<primaryStringField>` per linked triggers’ schemas; management create/patch + list expose `request_body_schema` / `body_fields` (see [p5_trigger-management-ui-body-schema.md](./p5_trigger-management-ui-body-schema.md)). Removing `raw_input` emission is still deferred until telemetry.

---

## Persistence & export

- **DB:** Continue using `request_body_schema` `jsonb`; store the canonical v1 object.
- **YAML / flat file:** Bootstrap and tenant exports should serialize the **same** object (pretty-printed JSON in YAML or native YAML mapping — product preference). The user-facing mental model is “flat JSON file” of field definitions; the **canonical** shape still uses the small envelope (`schema_version`, `fields`, optional `field_order`).

---

## Testing matrix (implementation checklist)

| Area | Cases |
|------|--------|
| API validation | Unknown field, wrong JSON type, empty name, duplicate names |
| Legacy ingest | Flat map + JSON Schema blob normalization |
| UI | Cannot paste invalid schema; type dropdown restricted; node preview matches saved schema |
| Bindings | Picker lists fields; resolver paths match payload after migration |
| E2E | POST trigger with body matching schema → run receives expected `trigger_payload` |

---

## Related documents

- [p5_trigger-ui-implementation-guide.md](./p5_trigger-ui-implementation-guide.md) — frontend implementation guide (Triggers page, schema editor, test invoke).
- [p5_trigger-management-ui-body-schema.md](./p5_trigger-management-ui-body-schema.md) — management API summary for `body_fields` / `request_body_schema`.
- [p5_input-binding-signal-picker-architecture.md](./p5_input-binding-signal-picker-architecture.md) — binding UX and `trigger.payload` paths.
- [phase-3-yaml-backed-product-model/index.md](../phase-3-yaml-backed-product-model/index.md) — trigger definition fields (`request_body_schema`).
- [phase-4-datastore-backed-definitions](../phase-4-datastore-backed-definitions/index.md) — datastore layout.

---

## Open decisions

1. **Minimum fields:** Must every HTTP POST trigger define at least one body field?
2. **Coercion:** Allow string-to-number for query-adjacent clients or stay strict JSON types?
3. **Rename policy:** Allow field renames when jobs already reference `trigger.payload.<old>`?
4. **OpenAPI:** Whether v2 generates `/triggers/{user_id}/{path}` request bodies from the same canonical model.
