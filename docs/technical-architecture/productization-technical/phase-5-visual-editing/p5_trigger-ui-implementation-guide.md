# Implementation guide: Triggers page — POST body schema (frontend)

This document is for the **product UI** in the sibling repository (e.g. `notion_pipeliner_ui`). **Authenticated users** (operators and regular users)—not an admin-only console—use that surface to manage HTTP triggers. It describes how to implement **create/edit/list** flows when each trigger has a **`request_body_schema`** that defines the JSON body callers must send to `POST /triggers/{user_id}{path}`.

**Companion (API contract, concise):** [p5_trigger-management-ui-body-schema.md](./p5_trigger-management-ui-body-schema.md)  
**Product/architecture context:** [p5_trigger-request-body-schema-architecture.md](./p5_trigger-request-body-schema-architecture.md)

---

## 1. Goals and scope

### In scope

- **List triggers** and show each trigger’s **body schema** in a human-readable way (field names, types, required, string max length where applicable).
- **Create trigger** with path, display name, and an optional **editable list of body fields** (default = single required string `keywords`, locations-compatible).
- **Edit trigger** schema and display name via **PATCH** (replace schema when user saves new field definitions).
- **Test invoke** UI: build a small form or JSON editor from the trigger’s schema so users can fire a real request with valid JSON.
- **Copy helpers** for integrators: e.g. “Sample JSON body”, “Binding path: `trigger.payload.<field>`”.

### Out of scope (defer unless product asks)

- Visual JSON Schema editor for arbitrary nested objects (backend today is mostly **flat** `properties`).
- Versioning or diffing schema changes against existing pipelines (backend may add validation later).
- OpenAPI / code generation from schema.

---

## 2. API recap (what the UI must call)

Assume existing **Bearer JWT** management auth (`Authorization: Bearer <access_token>`), same as other `/management/*` routes.

| Action | Method / path | Body | Response notes |
|--------|----------------|------|----------------|
| List | `GET /management/triggers` | — | Each item includes `request_body_schema` |
| Create | `POST /management/triggers` | `{ path, display_name?, body_fields? }` | Returns `secret` once + full `request_body_schema` |
| Update | `PATCH /management/triggers/{trigger_id}` | `{ display_name?, body_fields? }` | Replacing schema requires sending **full** `body_fields` list when user edits schema |
| Rotate secret | `POST /management/triggers/{trigger_id}/rotate-secret` | — | Unchanged |

**Invoke (test only):** `POST /triggers/{user_id}/{path}` with `Authorization: Bearer <trigger_secret>` and JSON body matching that trigger’s schema. Use the **user_id** and **path** from your app (same as today). Do not use the management JWT for invoke — use the **trigger secret** (per-row `secret` from list, or returned on create/rotate).

Full field shapes: see [p5_trigger-management-ui-body-schema.md](./p5_trigger-management-ui-body-schema.md).

---

## 3. Recommended TypeScript types

Define types in the UI repo (names illustrative):

```typescript
/** Single row in create/patch payload */
export type TriggerBodyFieldDraft = {
  name: string;
  type: "string" | "number" | "boolean";
  required: boolean;
  max_length?: number; // strings only
};

/** GET list item (subset) */
export type ManagementTriggerItem = {
  id: string;
  display_name: string;
  path: string;
  method: string;
  status: string;
  auth_mode: string;
  secret: string;
  secret_last_rotated_at: string | null;
  updated_at: string | null;
  request_body_schema: Record<string, unknown>;
};

export type CreateManagementTriggerPayload = {
  path: string;
  display_name?: string;
  body_fields?: TriggerBodyFieldDraft[];
};

export type PatchManagementTriggerPayload = {
  display_name?: string;
  body_fields?: TriggerBodyFieldDraft[];
};
```

Keep **snake_case** in JSON payloads to match the API; use camelCase only inside React state if that is your convention—**normalize at the API boundary**.

---

## 4. Normalizing `request_body_schema` for editing

The backend may return:

1. **Canonical JSON Schema** — `{ type: "object", required: [...], properties: { ... } }` (preferred after create/patch).
2. **Legacy flat map** — e.g. `{ "keywords": "string" }` from older rows.

The editor should **convert to `TriggerBodyFieldDraft[]`** for the form, and **only send `body_fields`** on save (let the API produce canonical JSON Schema).

### 4.1 Parse JSON Schema → drafts

Algorithm:

1. If `schema.properties` is an object:
   - For each key in `properties`, read `spec.type` (`string` | `number` | `boolean`; default `string` if missing).
   - `required`: `true` if `schema.required` is an array containing this key.
   - `max_length`: from `spec.maxLength` if `type === "string"`.
2. **Stable field order:** use `Object.keys(properties)` in API order, or sort alphabetically for display—pick one and stay consistent.
3. If the schema is **not** parseable (empty, unknown shape), show a **read-only JSON** fallback + message: “Edit schema in a future release” or prompt user to **re-save** via PATCH with a fresh `body_fields` list built from defaults.

### 4.2 Parse flat map → drafts

If `properties` is absent but keys look like `keywords: "string"`:

- For each key `k` with value `"string"` | `"number"` | `"boolean"`, map to the same type.
- Treat all flat-map keys as **required** unless you later extend the API.

### 4.3 Default when creating “simple” trigger

If the user does not customize fields, **omit `body_fields`** on create so the backend applies the default **keywords** schema (matches `/locations`).

---

## 5. API client functions

Add (or extend) a small module, e.g. `api/managementTriggers.ts`:

```typescript
const jsonHeaders = (accessToken: string) => ({
  Authorization: `Bearer ${accessToken}`,
  "Content-Type": "application/json",
});

export async function getManagementTriggers(accessToken: string) {
  const r = await fetch(`${API_BASE}/management/triggers`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!r.ok) throw await errorFromResponse(r);
  return r.json() as Promise<{ items: ManagementTriggerItem[] }>;
}

export async function createManagementTrigger(
  accessToken: string,
  body: CreateManagementTriggerPayload,
) {
  const r = await fetch(`${API_BASE}/management/triggers`, {
    method: "POST",
    headers: jsonHeaders(accessToken),
    body: JSON.stringify(body),
  });
  if (!r.ok) throw await errorFromResponse(r);
  return r.json();
}

export async function patchManagementTrigger(
  accessToken: string,
  triggerId: string,
  body: PatchManagementTriggerPayload,
) {
  const r = await fetch(`${API_BASE}/management/triggers/${encodeURIComponent(triggerId)}`, {
    method: "PATCH",
    headers: jsonHeaders(accessToken),
    body: JSON.stringify(body),
  });
  if (!r.ok) throw await errorFromResponse(r);
  return r.json();
}
```

**Errors:** Map `400` / `422` to inline form errors; show `detail` string from JSON when present.

---

## 6. UX flows

### 6.1 Triggers list (read)

- Add a column **“POST body”** or expand row: show comma-separated list like `keywords: string (required)` or multi-line for many fields.
- Optional **“Copy sample JSON”** button: build `{ [name]: defaultValue }` with `""`, `0`, `false` as placeholders.

### 6.2 Create trigger modal

Fields:

1. **Path** (required) — normalize UX to always show a leading `/`; strip duplicates client-side if user types `/foo` and you also prepend.
2. **Display name** (optional).
3. **Body fields** (optional advanced section):
   - **“Use default (keywords only)”** — checkbox **on** by default → do **not** send `body_fields`.
   - When **off**, show **Field list** (§7).
4. On success: show **secret** once (existing pattern: reveal/mask, copy); persist nothing secret in localStorage.

### 6.3 Edit trigger

- **Display name** inline or modal.
- **Body schema:** “Edit JSON body fields” opens the same **Field list** editor seeded from normalized `request_body_schema`.
- **Save** → `PATCH` with full `body_fields` array whenever the schema section is dirty.
- Warn if user removes a field that might be referenced in pipelines (`trigger.payload.old`) — v1 can be a soft **informational** banner (“Update pipeline bindings if you rename or remove fields”).

### 6.4 Test invoke modal (high value)

Today many UIs hardcode `{ keywords }`. Change to:

1. Load selected trigger’s `request_body_schema`.
2. Build:
   - Either **dynamic form** (one control per property), or
   - **Monaco / textarea** with pre-filled sample JSON (validate with a small AJV or hand-rolled validator matching backend rules for v1).
3. POST to `BASE_URL/triggers/${userId}/${pathWithoutLeadingSlash}` with `Authorization: Bearer ${trigger.secret}`.
4. Show response status + body; surface **400** validation errors from API `detail`.

**userId:** Use the same identifier as the rest of the app (e.g. Supabase `user.id` UUID string).

---

## 7. Field list component (design)

Suggested subcomponents:

| Piece | Responsibility |
|--------|------------------|
| `TriggerBodyFieldsEditor` | Holds `TriggerBodyFieldDraft[]`; add/remove/reorder rows |
| Row | `name` text, `type` select, `required` checkbox, `max_length` number (strings only) |
| Validation | Block save if duplicate names, empty names, invalid identifiers (recommend `^[a-zA-Z][a-zA-Z0-9_]*$` client-side to match typical JSON keys) |

**Reorder:** drag handles optional; order affects display only (backend does not guarantee property iteration order in all JSON parsers—in practice modern browsers preserve key order for object literals).

**Limits:** Optionally cap number of fields (e.g. 20) to avoid accidental huge schemas.

---

## 8. Client-side validation (mirror backend)

Align with backend behavior to reduce round-trips:

- **name:** non-empty, unique, safe JSON key characters.
- **type:** only three enums.
- **required:** boolean.
- **max_length:** positive integer, only when type is `string`; optional.

Before PATCH, if `body_fields` is empty array, **either** block with error **or** omit sending `body_fields` (means “don’t change schema”)—**do not** send `[]` if the API rejects empty field lists for replacement.

---

## 9. Binding path hints (pipeline editor)

Where you document or show **signal** paths for step inputs:

- For each string field `foo` in `request_body_schema`, show: **`trigger.payload.foo`**
- Link to [p5_input-binding-signal-picker-architecture.md](./p5_input-binding-signal-picker-architecture.md) if present.

This helps users after they rename fields in the trigger schema.

---

## 10. Testing (frontend)

| Test | What to assert |
|------|----------------|
| Create default | POST body has no `body_fields`; list shows `keywords` in schema |
| Create custom | POST includes `body_fields`; response `request_body_schema.properties` contains names |
| Normalization | Given mock JSON Schema response, editor shows correct rows |
| PATCH | Only changed sections; schema replace sends full `body_fields` |
| Invoke | Mock `fetch`: correct URL, Bearer secret header, JSON body keys |

Use **Vitest** + **MSW** or mock `global.fetch` consistent with existing dashboard tests (see work-log references to router/api tests).

---

## 11. Security and operational notes

- **Secrets:** List endpoint returns plaintext `secret` today (see tech-debt doc). Mask by default in UI; never log secrets.
- **CORS:** Invoke may hit a different origin in dev; ensure Vite proxy or allowed origins match how `triggerLocations` is called today.
- **Rate limiting:** Not required for v1; test invoke is low-frequency and user-initiated.

---

## 12. Implementation checklist (copy into a ticket)

- [ ] Types for triggers + `body_fields`
- [ ] `getManagementTriggers` / `createManagementTrigger` / `patchManagementTrigger`
- [ ] Normalizers: API schema → `TriggerBodyFieldDraft[]`
- [ ] `TriggerBodyFieldsEditor` + integrate create modal
- [ ] Edit schema on existing trigger (PATCH)
- [ ] List column or detail for human-readable schema summary
- [ ] Test invoke: dynamic body + correct auth
- [ ] Copy sample JSON + copy binding paths
- [ ] Tests for API client + one UI integration test
- [ ] Update in-app help / README link for integrators

---

## 13. File layout suggestion (UI repo)

Illustrative only—adapt to your structure:

```text
src/
  api/
    managementTriggers.ts       # fetch wrappers
  features/
    triggers/
      types.ts
      schemaNormalize.ts        # request_body_schema → drafts
      TriggerBodyFieldsEditor.tsx
      CreateTriggerModal.tsx
      EditTriggerSchemaModal.tsx
      InvokeTriggerModal.tsx
      TriggersPage.tsx
```

---

## 14. Open follow-ups (backend / product)

- PATCH semantics for “clear all optional fields” vs partial updates to individual property metadata.
- Server-side validation that **renames** don’t break linked jobs (today: user responsibility).
- Returning a **canonical** schema only in list responses for all rows (migration job for legacy flat maps).

When those land, update this guide and the list normalizer accordingly.
