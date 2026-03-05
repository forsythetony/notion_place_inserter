# Rate Limits

The API enforces two types of limits:

1. **Rate limits** — Maximum API requests over a defined period
2. **Spend limits** — Maximum monthly cost for API usage

Limits apply at the organization level. You can also set user-configurable limits per workspace.

## Key Concepts

- Limits represent **maximum allowed usage**, not guaranteed minimums
- Uses the [token bucket algorithm](https://en.wikipedia.org/wiki/Token_bucket) — capacity replenishes continuously
- Limits increase automatically as you reach usage thresholds
- View your limits in the [Claude Console Limits page](https://docs.anthropic.com/settings/limits)

## Spend Limits

Each tier has a monthly spend limit. To advance tiers, meet the credit purchase requirement:

| Tier | Credit Purchase to Advance | Max Credit Purchase |
|------|---------------------------|---------------------|
| Tier 1 | $5 | $100 |
| Tier 2 | $40 | $500 |
| Tier 3 | $200 | $1,000 |
| Tier 4 | $400 | $5,000 |

## Rate Limits (Messages API)

Measured in RPM (requests per minute), ITPM (input tokens per minute), and OTPM (output tokens per minute) per model class.

### Cache-Aware ITPM

**Cached tokens do NOT count toward ITPM** for most models. Only these count:

- `cache_creation_input_tokens` ✓
- `input_tokens` (after last cache breakpoint) ✓
- `cache_read_input_tokens` ✗ (for most models)

This makes [prompt caching](https://docs.anthropic.com/docs/en/build-with-claude/prompt-caching) effective for increasing throughput.

### Tier 1 (Example)

| Model | RPM | ITPM | OTPM |
|-------|-----|------|------|
| Claude Opus 4.x | 50 | 30,000 | 8,000 |
| Claude Sonnet 4.x | 50 | 30,000 | 8,000 |
| Claude Haiku 4.5 | 50 | 50,000 | 10,000 |

### Tier 4 (Example)

| Model | RPM | ITPM | OTPM |
|-------|-----|------|------|
| Claude Opus 4.x | 4,000 | 2,000,000 | 400,000 |
| Claude Sonnet 4.x | 4,000 | 2,000,000 | 400,000 |
| Claude Haiku 4.5 | 4,000 | 4,000,000 | 800,000 |

*Opus and Sonnet limits are shared across their respective model families.*

## Rate Limit Errors

Exceeding limits returns a **429** error with a `retry-after` header indicating how long to wait.

## Response Headers

| Header | Description |
|-------|-------------|
| `retry-after` | Seconds to wait before retrying |
| `anthropic-ratelimit-requests-limit` | Max requests allowed |
| `anthropic-ratelimit-requests-remaining` | Requests remaining |
| `anthropic-ratelimit-requests-reset` | When limit replenishes (RFC 3339) |
| `anthropic-ratelimit-input-tokens-limit` | Max input tokens |
| `anthropic-ratelimit-input-tokens-remaining` | Input tokens remaining |
| `anthropic-ratelimit-output-tokens-limit` | Max output tokens |
| `anthropic-ratelimit-output-tokens-remaining` | Output tokens remaining |

## Message Batches API

Separate rate limits apply: RPM to endpoints and a limit on batch requests in the processing queue.

## Workspace Limits

Set lower spend and rate limits per workspace to protect other workspaces from overuse. Organization-wide limits always apply.
