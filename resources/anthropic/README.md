# Anthropic API Documentation

This folder contains documentation for interacting with the [Anthropic API](https://docs.anthropic.com/), pulled from the official docs and stored as markdown for reference.

## Contents

| File | Description |
|------|-------------|
| [getting-started.md](getting-started.md) | API overview, authentication, prerequisites, basic example |
| [models.md](models.md) | Models API — list and retrieve available models |
| [messages-api.md](messages-api.md) | Messages API — send messages, parameters, message format |
| [streaming.md](streaming.md) | Streaming responses with SSE |
| [rate-limits.md](rate-limits.md) | Rate limits, spend limits, tier structure |
| [api-features.md](api-features.md) | Features overview — tools, context, model capabilities |
| [tool-use.md](tool-use.md) | Tool use — defining tools, tool flow, examples |
| [errors.md](errors.md) | HTTP errors, error format, common validation errors |

## Source

Documentation sourced from:

- https://docs.anthropic.com/en/api/getting-started
- https://docs.anthropic.com/en/api/models
- https://docs.anthropic.com/en/api/messages
- https://docs.anthropic.com/en/docs/build-with-claude/streaming
- https://docs.anthropic.com/en/api/rate-limits
- https://docs.anthropic.com/en/docs/resources/api-features
- https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview
- https://docs.anthropic.com/en/api/errors

## Quick Start

```python
from anthropic import Anthropic

client = Anthropic()
message = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello, Claude"}],
)
```
