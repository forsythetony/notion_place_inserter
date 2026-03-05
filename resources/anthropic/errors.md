# API Errors

## HTTP Error Codes

| Code | Type | Description |
|------|------|-------------|
| 400 | `invalid_request_error` | Issue with format or content of request |
| 401 | `authentication_error` | Issue with API key |
| 403 | `permission_error` | API key lacks permission for resource |
| 404 | `not_found_error` | Requested resource not found |
| 413 | `request_too_large` | Request exceeds size limit (32 MB standard, 256 MB batch, 500 MB files) |
| 429 | `rate_limit_error` | Account hit rate limit |
| 500 | `api_error` | Unexpected internal error |
| 529 | `overloaded_error` | API temporarily overloaded |

## Request Size Limits

| Endpoint | Maximum Size |
|----------|--------------|
| Messages API | 32 MB |
| Token Counting API | 32 MB |
| Batch API | 256 MB |
| Files API | 500 MB |

413 errors are returned from Cloudflare before the request reaches API servers.

## Error Response Format

Errors are returned as JSON with a top-level `error` object:

```json
{
  "type": "error",
  "error": {
    "type": "not_found_error",
    "message": "The requested resource could not be found."
  },
  "request_id": "req_011CSHoEeqs5C35K2UUqR7Fy"
}
```

Always includes `type` and `message`. Include `request_id` when contacting support.

## Request ID

Every response includes a unique `request-id` header (e.g., `req_018EeWyXxfu5pfWkrYcMdjWG`). SDKs expose this as `_request_id` on response objects.

## Rate Limit (429)

When rate limited, the response includes a `retry-after` header with seconds to wait. Ramp up traffic gradually to avoid acceleration limits.

## Long Requests

For requests over 10 minutes:

- Use **streaming** or **Message Batches API**
- Avoid large `max_tokens` without streaming—networks may drop idle connections
- SDKs validate non-streaming requests against 10-minute timeout and set TCP keep-alive

Use `.stream()` with `.get_final_message()` (Python) or `.finalMessage()` (TypeScript) for large outputs without event handling.

## Common Validation Errors

### Prefill Not Supported

Claude Opus 4.6 does not support prefilling assistant messages. Returns 400:

```json
{
  "type": "error",
  "error": {
    "type": "invalid_request_error",
    "message": "Prefilling assistant messages is not supported for this model."
  }
}
```

Use structured outputs, system prompt instructions, or `output_config.format` instead.

## Streaming Errors

When streaming via SSE, errors can occur after a 200 response. Error handling may not follow standard mechanisms in that case.
