# Models API

## List Models

**GET** `/v1/models`

List available models. More recently released models are listed first.

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | number | Items per page (1-1000). Default: 20 |
| `before_id` | string | Cursor for pagination (previous page) |
| `after_id` | string | Cursor for pagination (next page) |

### Response

| Field | Description |
|-------|-------------|
| `data` | Array of ModelInfo objects |
| `last_id` | Last ID in data (use as `after_id` for next page) |
| `first_id` | First ID in data (use as `before_id` for previous page) |
| `has_more` | Whether more results exist |

### ModelInfo

| Field | Description |
|-------|-------------|
| `id` | Unique model identifier |
| `created_at` | RFC 3339 datetime (release time) |
| `display_name` | Human-readable model name |
| `type` | Always `"model"` |

### Example

```bash
curl https://api.anthropic.com/v1/models \
  -H 'anthropic-version: 2023-06-01' \
  -H "X-Api-Key: $ANTHROPIC_API_KEY"
```

## Retrieve Model

**GET** `/v1/models/{model_id}`

Get a specific model. Use model identifier or alias.

### Path Parameters

| Parameter | Description |
|-----------|-------------|
| `model_id` | Model identifier or alias |

### Example

```bash
curl https://api.anthropic.com/v1/models/$MODEL_ID \
  -H 'anthropic-version: 2023-06-01' \
  -H "X-Api-Key: $ANTHROPIC_API_KEY"
```

## Beta Headers

Use the `anthropic-beta` header to access beta features. Example values:

- `message-batches-2024-09-24`
- `prompt-caching-2024-07-31`
- `files-api-2025-04-14`
- `context-1m-2025-08-07`
- `skills-2025-10-02`
- And more—see API reference for full list
