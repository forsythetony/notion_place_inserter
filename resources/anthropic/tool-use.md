# Tool Use with Claude

Claude can interact with tools and functions, extending its capabilities. You specify what operations are available; Claude decides when and how to call them.

## Strict Tool Use

Add `strict: true` to tool definitions for guaranteed schema validation. Claude's tool calls will always match your schema exactly—no type mismatches or missing fields. Ideal for production agents.

## Basic Example

### cURL

```bash
curl https://api.anthropic.com/v1/messages \
  -H "content-type: application/json" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-opus-4-6",
    "max_tokens": 1024,
    "tools": [
      {
        "name": "get_weather",
        "description": "Get the current weather in a given location",
        "input_schema": {
          "type": "object",
          "properties": {
            "location": {
              "type": "string",
              "description": "The city and state, e.g. San Francisco, CA"
            }
          },
          "required": ["location"]
        }
      }
    ],
    "messages": [
      {"role": "user", "content": "What is the weather like in San Francisco?"}
    ]
  }'
```

### Python

```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1024,
    tools=[
        {
            "name": "get_weather",
            "description": "Get the current weather in a given location",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    }
                },
                "required": ["location"],
            },
        }
    ],
    messages=[{"role": "user", "content": "What's the weather like in San Francisco?"}],
)
```

## Tool Definition Format

Each tool has:

| Field | Description |
|-------|-------------|
| `name` | Unique tool identifier |
| `description` | What the tool does (Claude uses this to decide when to call) |
| `input_schema` | JSON Schema for the tool's parameters |

## Tool Use Flow

1. **Request** — Send messages with `tools` array
2. **Response** — Claude may return `tool_use` blocks in `content`
3. **Execute** — Run the tool with the provided parameters
4. **Continue** — Append a message with `role: "user"` and `content` containing `tool_result` blocks
5. **Repeat** — Send another request with the full message history until `stop_reason` is `"end_turn"`

## Tool Result Format

```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_01...",
  "content": "72°F, partly cloudy"
}
```

Or for errors:

```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_01...",
  "is_error": true,
  "content": "Weather service unavailable"
}
```

## Server-Side vs Client-Side Tools

- **Server-side** (Code execution, Memory, Web fetch, Web search): Run by Anthropic's platform
- **Client-side** (Bash, Computer use, Text editor, custom tools): You implement and execute, return results via `tool_result`
