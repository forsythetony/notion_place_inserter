# Audit: `keywords` vs dynamic trigger / step input refs

**Date:** 2026-03-20  
**Reader:** Engineering (pipeline execution, triggers, queue, UI)  
**Intent:** Inventory every place we still *depend on* the name `keywords`, distinguish that from **unrelated** uses (parameter names, CSS classes), and define the target model: **schema-driven `trigger.payload.<field>` + `step.<id>.<output>`**, with no special-casing for a field called `keywords`.

---

## Target model (already supported)

- **Step inputs** are arbitrary keys (`query`, `value`, `source_value`, …) resolved via `input_bindings` → `signal_ref` | `static_value` | `cache_key_ref` | `target_schema_ref` (`app/services/job_execution/binding_resolver.py`).
- **Trigger-side values** use dotted refs: `trigger.payload.<bodyFieldName>` matching the linked trigger’s `request_body_schema`.
- **Save-time migration** already rewrites `trigger.payload.raw_input` → `trigger.payload.<primaryStringField>` when all linked triggers agree on one primary string field (`app/services/trigger_binding_migration.py`, `validation_service._maybe_migrate_legacy_trigger_bindings`). That migration is **not** hardcoded to `keywords`; it uses `primary_string_field_for_legacy_mapping`.

**Pipeline step handlers** under `app/services/job_execution/handlers/` do **not** reference the string `keywords`; they consume `resolved_inputs` only. No handler change is required purely to “stop using keywords” in step logic.

---

## Category A — Trigger HTTP body field name `keywords` (product default)

These assume the **POST body** has a property literally named `keywords` (locations-era compatibility).

| Location | Role |
|----------|------|
| `app/services/trigger_request_body.py` | `default_keywords_request_body_schema()` — default trigger schema with required `keywords` string. |
| `app/routes/management.py` | Trigger create / live-test: fallback schema when trigger has no `request_body_schema`; docs mention “keywords”. |
| `app/routes/locations.py` | Legacy `/places` path: `_legacy_keywords_from_body` reads `body["keywords"]`. |
| `notion_pipeliner_ui` `TriggersPage.tsx`, `DashboardTrigger.tsx`, `api.ts` `triggerLocations` | Default create flow and legacy dashboard still center the **label** and **field name** `keywords`. |

**Direction:** Treat `keywords` as **one possible field name**, not the platform default forever. Prefer:

- Rename default to something neutral in docs/UI (e.g. “primary search text” field with a **user-defined name**), **or**
- Keep `default_keywords_request_body_schema()` as a **preset** but stop presenting it as the only “right” shape in copy.

---

## Category B — Queue message + run persistence (legacy envelope)

The worker accepts old messages where only a top-level `keywords` string existed (no `trigger_payload`).

| Location | Role |
|----------|------|
| `app/queue/worker.py` `_extract_payload` | If `trigger_payload` missing, uses `p["keywords"]` and rebuilds payload via `default_keywords_request_body_schema`. |
| `app/routes/locations.py`, `app/routes/management.py` | Enqueue payloads still set a top-level `"keywords": log_preview` for logging / legacy consumers. |
| `app/repositories/postgres_run_repository.py` | Optional `keywords=` path when persisting runs — validates with default keywords schema. |
| `app/services/run_lifecycle_adapter.py` | Same pattern. |
| `app/queue/models.py`, `app/services/supabase_run_repository.py` | Typed envelopes still say `keywords`. |
| `app/queue/events.py`, `app/services/communicator.py` | `PipelineFailureEvent` / WhatsApp copy use `event.keywords` as a **human preview** string. |

**Direction:**

- Long term: top-level queue field could be renamed to `trigger_preview` / `input_preview` or dropped when `trigger_payload` is always present.
- Short term: keep backward compatibility for in-flight messages; new producers should prefer **only** `trigger_payload` + optional non-confusing metadata.

---

## Category C — Binding resolver special cases

| Location | Role |
|----------|------|
| `app/services/job_execution/binding_resolver.py` | Docs cite `trigger.payload.keywords`; **fallback**: if `keywords` absent but `raw_input` present, resolve `trigger.payload.keywords` to `raw_input` (legacy pipelines + non-keywords schemas). |

**Direction:** Prefer bindings that point to **`trigger.payload.<actualField>`** from the trigger schema. The fallback is compatibility glue; a **second migration** could rewrite `trigger.payload.keywords` → `trigger.payload.<primary_string_field>` on save (same pattern as `raw_input` migration), then tighten or remove the resolver fallback.

---

## Category D — Docs / examples / live-test samples

| Location | Role |
|----------|------|
| `p5_pipeline-live-testing-architecture.md` | Examples use `"keywords": "coffee shops"`. |
| Deprecation log in `trigger_request_body.py` | Example still says `trigger.payload.keywords`. |

**Direction:** Update examples to generic `trigger.payload.<field>` or multi-field JSON.

---

## Category E — Unrelated “keywords” (no semantic coupling)

These use “keywords” as a **variable name** or **UI CSS class**, not as the trigger field name:

| Location | Notes |
|----------|--------|
| `app/services/places_service.py` | Parameter `keywords` = search query text for Places pipeline (rename to `query` internally for clarity only). |
| `app/pipeline_lib/logging.py`, `app/main.py` | `keywords_preview` = short string preview for logs. |
| `notion_pipeliner_ui` `.keywords-field`, `.keywords-hint` | CSS hooks; rename only if rebranding UI. |

---

## UI binding picker (already aligned)

`notion_pipeliner_ui/src/lib/availableSignals.ts` builds `trigger.payload.<field>` from the linked trigger’s schema when resolved; it also offers **legacy** `trigger.payload.raw_input`. It does **not** require a field named `keywords`.

---

## Recommended phases

1. **Contracts** — Document that step bindings must use **`trigger.payload.<schema field>`** or step outputs; list `raw_input` / old `keywords` refs as deprecated.
2. **Save-time migration (optional)** — Extend `migrate_raw_input_signal_refs_for_steps` pattern to rewrite `trigger.payload.keywords` → `trigger.payload.<primary_string_field>` when unambiguous (all linked triggers share one primary string field and it is not `keywords`).
3. **Queue / events** — Introduce neutral naming (`input_preview`) alongside `keywords` for events; deprecate top-level queue `keywords` after a migration window.
4. **UI** — Replace “keywords mode” copy with “default single string field” or schema-first language; keep API compatibility for existing triggers.
5. **Remove resolver fallback** — After DB snapshots no longer store `trigger.payload.keywords` for non-keywords schemas, remove the `keywords`→`raw_input` fallback in `binding_resolver.py`.

---

## Related docs

- `p5_trigger-request-body-schema-architecture.md`
- `trigger_binding_migration.py` / `validation_service.py` (save-time ref migration)
- `binding_resolver.py` (runtime resolution)
