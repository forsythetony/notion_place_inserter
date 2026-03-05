# Anthropic API Overview

The Claude API is a RESTful API at `https://api.anthropic.com` that provides programmatic access to Claude models. The primary API is the **Messages API** (`POST /v1/messages`) for conversational interactions.

## Prerequisites

- An [API key](https://docs.anthropic.com/settings/keys)
- An [Anthropic Console account](https://platform.claude.com/)

## Available APIs

### General Availability

| API | Endpoint | Description |
|-----|----------|--------------|
| Messages API | `POST /v1/messages` | Send messages to Claude for conversational interactions |
| Models API | `GET /v1/models` | List available Claude models and their details |
| Token Counting API | `POST /v1/messages/count_tokens` | Count tokens before sending to manage costs |
| Message Batches API | `POST /v1/messages/batches` | Process large volumes asynchronously (50% cost reduction) |

### Beta

| API | Endpoint | Description |
|-----|----------|-------------|
| Skills API | `POST /v1/skills`, `GET /v1/skills` | Create and manage custom agent skills |
| Files API | `POST /v1/files`, `GET /v1/files` | Upload and manage files for multiple API calls |

## Authentication

All requests must include these headers:

| Header | Value | Required |
|--------|-------|----------|
| `x-api-key` | Your API key from Console | Yes |
| `anthropic-version` | API version (e.g., `2023-06-01`) | Yes |
| `content-type` | `application/json` | Yes |

### Getting API Keys

Generate API keys in [Account Settings](https://platform.claude.com/settings/keys). Use [workspaces](https://platform.claude.com/settings/workspaces) to segment keys and control spend by use case.

## Client SDKs

Anthropic provides official SDKs for Python, TypeScript, Java, Go, C#, Ruby, and PHP. Benefits:

- Request timeouts and connection management
- Streaming support
- Built-in retry logic and error handling
- Type-safe request and response handling
- Automatic header management

### Python Example

```python
from anthropic import Anthropic

client = Anthropic()  # Reads ANTHROPIC_API_KEY from environment
message = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello, Claude"}],
)
```

## Request and Response Format

### Request Size Limits

| Endpoint | Maximum Size |
|----------|--------------|
| Standard (Messages, Token Counting) | 32 MB |
| Batch API | 256 MB |
| Files API | 500 MB |

Exceeding limits returns a 413 `request_too_large` error.

### Response Headers

- `anthropic-organization-id`: Organization ID for the API key
- `request-id`: Globally unique identifier for the request

## Basic Example (cURL)

```bash
curl https://api.anthropic.com/v1/messages \
  --header "x-api-key: $ANTHROPIC_API_KEY" \
  --header "anthropic-version: 2023-06-01" \
  --header "content-type: application/json" \
  --data '{
    "model": "claude-opus-4-6",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "Hello, Claude"}
    ]
  }'
```

### Example Response

```json
{
  "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "Hello! How can I assist you today?"
    }
  ],
  "model": "claude-opus-4-6",
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 12,
    "output_tokens": 8
  }
}
```

## Rate Limits and Availability

The API enforces rate limits (RPM, ITPM, OTPM) and spend limits. Limits increase automatically as you use the API. View your limits in the [Console](https://docs.anthropic.com/settings/limits).

The API is available in [many countries and regions](https://docs.anthropic.com/docs/en/api/supported-regions) worldwide.

## Claude API vs Third-Party Platforms

| Option | Best For |
|--------|----------|
| **Claude API** | New integrations, full feature access, direct Anthropic relationship |
| **AWS Bedrock** | Existing AWS infrastructure, consolidated cloud billing |
| **Vertex AI** | Google Cloud infrastructure |
| **Azure AI** | Microsoft Azure infrastructure |

Third-party platforms may have feature delays or differences from the direct API.
