# Streaming Messages

Set `stream: true` when creating a Message to incrementally stream the response using [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events) (SSE).

## Python SDK

```python
import anthropic

client = anthropic.Anthropic()

with client.messages.stream(
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
    model="claude-opus-4-6",
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

## TypeScript SDK

```typescript
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();

await client.messages
  .stream({
    messages: [{ role: "user", content: "Hello" }],
    model: "claude-opus-4-6",
    max_tokens: 1024
  })
  .on("text", (text) => {
    console.log(text);
  });
```

## Get Final Message Without Handling Events

For large `max_tokens` values, use streaming under the hood but get the complete `Message` object. This avoids HTTP timeouts without writing event-handling code:

### Python

```python
with client.messages.stream(
    max_tokens=128000,
    messages=[{"role": "user", "content": "Write a detailed analysis..."}],
    model="claude-opus-4-6",
) as stream:
    message = stream.get_final_message()

print(message.content[0].text)
```

### TypeScript

```typescript
const stream = client.messages.stream({
  max_tokens: 128000,
  messages: [{ role: "user", content: "Write a detailed analysis..." }],
  model: "claude-opus-4-6"
});
const message = await stream.finalMessage();
```

## SDK Support

- **Python**: Sync and async streams
- **TypeScript**: Event-based streaming
- **PHP**: `createStream()` method
- **Go, Java, C#, Ruby**: See respective SDK documentation

## Long Requests

For requests over 10 minutes, prefer:

- **Streaming Messages API** — Process tokens as they arrive
- **Message Batches API** — Poll for results, no uninterrupted connection needed

Some networks drop idle connections. The SDKs validate non-streaming requests against a 10-minute timeout and set TCP keep-alive.
