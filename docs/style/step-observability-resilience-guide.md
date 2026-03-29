# Building Observable, Resilient Steps

Date: 2026-03-29  
Status: Draft

This is a small engineering note for step authors. The goal is not to define every runtime rule up front; it is to make new steps easier to debug, safer to operate, and more consistent with the orchestrator.

## Core Rules

- A service should log enough detail to explain what happened in the service boundary.
- A step handler should turn service failures into structured step failures or degraded results that the orchestrator can understand.
- Logs should tell the story of the step in order: input, config, service work, output, and cost.

## 1. Service Error Responses

When a service fails, prefer returning or raising enough structured detail that the step can build a clean runtime error. Avoid vague errors like "request failed" unless the lower-level detail is already logged.

At minimum, capture:

- `service`: stable service name such as `ClaudeService`
- `operation`: what the service was trying to do
- `message`: short human-readable summary
- `details`: safe structured context such as status code, provider name, or parsed response body
- `retryable`: whether the step may reasonably retry later

The service log line should use the `[<Service>]` prefix and describe the service-local failure:

```text
[ClaudeService] prompt_completion failed service=ClaudeService operation=prompt_completion status_code=429 retryable=true
```

The step runtime log line should use the `[StepRuntime]` prefix and describe the step-level consequence:

```text
[StepRuntime] step failed step_template=step_template_ai_prompt service=ClaudeService operation=prompt_completion retryable=true
```

This split matters:

- `[<Service>]` logs explain the dependency failure.
- `[StepRuntime]` logs explain how that failure affected the step.

## 2. Propagating Errors To The Orchestrator

Do not swallow service exceptions inside the handler unless the step is explicitly designed to degrade gracefully.

Preferred pattern:

1. Service call fails with structured detail.
2. Handler catches it at the step boundary.
3. Handler returns or raises a structured step error with the important service context preserved.
4. Orchestrator records the step as failed or degraded without losing the original cause.

Use degraded results only when the step template has a clear fallback contract. If the step cannot produce a trustworthy output, fail it and let the orchestrator decide what to do next.

## 3. Logging Inputs, Config, Outputs, And Cost

Every step should log the smallest set of fields needed to reconstruct the run:

- Input summary: which upstream values were used, preferably summarized rather than dumping large payloads
- Configuration summary: the effective config that shaped behavior
- Output summary: what the step produced
- Cost summary: tokens, model/provider usage, API cost estimate, or other billable work when available

Good logging is:

- Structured
- Ordered
- Safe for production logs
- Small enough to scan quickly

Avoid logging:

- Full secrets or auth headers
- Large raw payloads unless temporarily debugging
- Duplicated blobs in both service and step-runtime logs

## Minimal Checklist

Before shipping a new step, confirm:

- Service failures include service name, operation, message, details, and retryability
- Handler converts failures into orchestrator-friendly step results
- `[<Service>]` and `[StepRuntime]` logs each have a clear job
- Input, config, output, and cost are logged in summarized form
- Fallback behavior is explicit when using degraded success

## Next Expansion

If this note proves useful, the next version should add:

- A concrete reference pattern for `StepExecutionResult`
- A standard shape for structured step errors
- Do and do-not examples from real handlers
- Guidance on redaction and log size limits
