# Triggers UI: HTTP POST body schema (management API)

The **Pipeliner UI** (sibling repo, e.g. `notion_pipeliner_ui`) should let **authenticated product users**—not a separate admin app—define the JSON body shape for each HTTP trigger. Runtime invocation (`POST /triggers/{user_id}{path}`) validates the client JSON against `request_body_schema` and builds `trigger_payload` with the same keys.

**Step-by-step frontend build:** [p5_trigger-ui-implementation-guide.md](./p5_trigger-ui-implementation-guide.md) (types, normalizers, components, testing, checklist).

## API

### List triggers

`GET /management/triggers` → each item includes:

- `request_body_schema` — JSON Schema object (`type`, `required`, `properties`) after create/patch (or legacy flat maps from older rows).

### Create trigger

`POST /management/triggers`

```json
{
  "path": "/my-webhook",
  "display_name": "Optional label",
  "body_fields": [
    { "name": "message", "type": "string", "required": true, "max_length": 2000 },
    { "name": "priority", "type": "number", "required": false }
  ]
}
```

Omit `body_fields` to get the default **locations-compatible** schema: one required string `keywords` with `minLength` 1 and `maxLength` 300.

Response includes `request_body_schema` and `secret` (shown once).

### Update trigger schema

`PATCH /management/triggers/{trigger_id}`

```json
{
  "display_name": "New label",
  "body_fields": [
    { "name": "title", "type": "string", "required": true }
  ]
}
```

When `body_fields` is present, it **replaces** the entire derived `request_body_schema`. Omitted fields on PATCH are left unchanged.

### Field model (`body_fields` items)

| Property | Type | Notes |
|---------|------|--------|
| `name` | string | JSON key clients must send |
| `type` | `"string"` \| `"number"` \| `"boolean"` | |
| `required` | boolean | default true |
| `max_length` | number? | strings only; optional |

## UI suggestions

1. **Create trigger modal** — path, display name, and an editable list of body fields (add row / remove row), with type dropdown and required + max length for strings.
2. **Trigger detail / edit** — load `request_body_schema` from list response; either edit via the same field list or show read-only JSON for power users.
3. **Docs / copy field path** — for each string field, hint bindings: `trigger.payload.<name>`.

## Invocation

Clients must `POST` JSON whose keys match the schema (unknown keys are rejected). Example for default trigger:

```json
{ "keywords": "stone arch bridge minneapolis" }
```

Example for custom fields:

```json
{ "message": "Hello", "priority": 2 }
```
