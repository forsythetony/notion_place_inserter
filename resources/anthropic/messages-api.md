# Messages API

**POST** `/v1/messages`

Send a structured list of input messages with text and/or image content. The model generates the next message in the conversation. Supports single queries and stateless multi-turn conversations.

## Key Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | Model ID (e.g., `claude-opus-4-6`) |
| `max_tokens` | number | Yes | Maximum tokens to generate |
| `messages` | array | Yes | Input messages (alternating user/assistant) |
| `system` | string | No | System prompt (no "system" role in messages) |
| `tools` | array | No | Tool definitions for tool use |
| `stream` | boolean | No | Set `true` for streaming response |
| `inference_geo` | string | No | Data residency: `"global"` or `"us"` |

## Message Format

Each message has `role` and `content`:

```json
{"role": "user", "content": "Hello, Claude"}
```

Content can be a string (shorthand for one text block) or an array of content blocks:

```json
{"role": "user", "content": [{"type": "text", "text": "Hello, Claude"}]}
```

### Content Block Types

| Type | Description |
|------|-------------|
| `text` | Text content. Supports `cache_control` for prompt caching. |
| `image` | Image via base64 or URL. Supports JPEG, PNG, GIF, WebP. |
| `document` | PDF or plain text document |

### Multi-turn Example

```json
[
  {"role": "user", "content": "Hello there."},
  {"role": "assistant", "content": "Hi, I'm Claude. How can I help you?"},
  {"role": "user", "content": "Can you explain LLMs in plain English?"}
]
```

Consecutive same-role messages are combined into a single turn. Limit: 100,000 messages per request.

## Response

| Field | Description |
|-------|-------------|
| `id` | Message ID |
| `type` | `"message"` |
| `role` | `"assistant"` |
| `content` | Array of content blocks (text, tool_use) |
| `model` | Model used |
| `stop_reason` | `"end_turn"`, `"max_tokens"`, `"tool_use"`, etc. |
| `usage` | `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` |

## Tool Use Flow

When Claude uses tools, the response includes `tool_use` blocks. You must:

1. Execute the tool
2. Append a `tool_result` message with the results
3. Send another request with the updated message history

See [tool-use.md](tool-use.md) for details.
