"""AI Prompt step runtime handler."""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle
from app.services.job_execution.step_runtime_base import StepRuntime
from app.services.pipeline_live_test.api_overrides import consume_manual_api_response

_CONFIG_PREVIEW_MAX = 1200


def _preview_config_fragment(text: str, *, max_len: int = _CONFIG_PREVIEW_MAX) -> str:
    s = text if text is not None else ""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _config_summary_for_log(config: dict[str, Any], *, value: Any) -> str:
    """Human-readable config/value preview for step processing logs."""
    prompt = config.get("prompt", "")
    max_tokens = config.get("max_tokens", 1024)
    lw = config.get("limit_words", 0)
    delim = config.get("delimiter", " ")
    sanitize = bool(config.get("sanitize_output"))
    if value is None:
        val_preview = ""
    elif isinstance(value, dict):
        val_preview = _preview_config_fragment(json.dumps(value, default=str))
    else:
        val_preview = _preview_config_fragment(str(value))
    return (
        f"max_tokens={max_tokens}, limit_words={lw}, delimiter={delim!r}, "
        f"sanitize_output={sanitize}, "
        f"prompt_preview={_preview_config_fragment(str(prompt))!r}, "
        f"value_preview={val_preview!r}"
    )


def _log_claude_ai_prompt_service_trace(
    step_handle: StepExecutionHandle,
    claude: Any,
    *,
    result: str,
    max_tokens: int,
) -> None:
    """Emit ClaudeService request/response lines from trace or usage fallback."""
    trace_getter = getattr(claude, "get_last_ai_prompt_llm_trace", None)
    trace: dict[str, Any] | None = None
    if callable(trace_getter):
        raw = trace_getter()
        if isinstance(raw, dict):
            trace = raw

    if trace:
        step_handle.log_service_provider_llm_request(
            service_label="ClaudeService",
            model=str(trace.get("model", "")),
            max_tokens=trace.get("max_tokens", max_tokens),
            body_preview=str(trace.get("user_message", "")),
        )
        usage = trace.get("usage") if isinstance(trace.get("usage"), dict) else {}
        step_handle.log_service_provider_llm_success(
            service_label="ClaudeService",
            response_preview=str(trace.get("assistant_text", result or "")),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )
        return

    usage_getter = getattr(claude, "get_last_usage", None)
    usage: dict[str, Any] | None = None
    if callable(usage_getter):
        u = usage_getter()
        if isinstance(u, dict):
            usage = u
    if usage:
        step_handle.log_service_provider_llm_request(
            service_label="ClaudeService",
            model=str(usage.get("model", "")),
            max_tokens=max_tokens,
            body_preview="(preview unavailable; trace not recorded by service)",
        )
        step_handle.log_service_provider_llm_success(
            service_label="ClaudeService",
            response_preview=result or "",
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )
    else:
        step_handle.log_processing(
            "[ClaudeService] Completed prompt_completion (trace metadata unavailable)."
        )


def _coerce_limit_words(raw: Any) -> int:
    """Parse limit_words from config; invalid/missing -> 0 (no limit)."""
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _normalize_delimiter(raw: Any) -> str:
    """Default space; empty string falls back to space so split() is safe."""
    if raw is None:
        return " "
    s = str(raw)
    return s if s != "" else " "


def trim_ai_prompt_output(text: str, *, limit_words: Any, delimiter: Any) -> str:
    """
    After the model returns, optionally keep only the first `limit_words` segments
    when splitting by `delimiter`. `limit_words <= 0` means no trimming.
    """
    if not text:
        return text or ""
    lw = _coerce_limit_words(limit_words)
    if lw <= 0:
        return text
    delim = _normalize_delimiter(delimiter)
    parts = text.split(delim)
    return delim.join(parts[:lw])


def sanitize_ai_prompt_output(text: str) -> str:
    """
    Remove non-alphanumeric characters (including markdown asterisks), collapse
    whitespace, and lowercase the result.
    """
    if not text:
        return ""
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.lower()


class AiPromptHandler(StepRuntime):
    """Run a configurable AI prompt on an input value; output is the model's text response."""

    def _finalize_value(self, config: dict[str, Any], raw: str) -> str:
        trimmed = trim_ai_prompt_output(
            raw or "",
            limit_words=config.get("limit_words", 0),
            delimiter=config.get("delimiter", " "),
        )
        if config.get("sanitize_output"):
            return sanitize_ai_prompt_output(trimmed)
        return trimmed

    async def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        input_bindings: dict[str, Any],
        resolved_inputs: dict[str, Any],
        ctx: ExecutionContext,
        step_handle: StepExecutionHandle,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        value = resolved_inputs.get("value")
        prompt = config.get("prompt", "")

        if not prompt:
            logger.warning("ai_prompt_missing_prompt | step_id={}", step_id)
            return {"value": ""}

        manual = consume_manual_api_response(ctx, "claude.ai_prompt")
        if manual is not None:
            step_handle.log_processing("Using live-test manual API override (claude.ai_prompt).")
            if isinstance(manual, dict) and "value" in manual:
                out = manual.get("value", "")
                s = str(out) if out is not None else ""
            else:
                s = str(manual) if manual is not None else ""
            return {"value": self._finalize_value(config, s)}

        claude = ctx.get_service("claude")
        if not claude:
            logger.warning("ai_prompt_no_claude | step_id={}", step_id)
            return {"value": ""}

        max_tokens = config.get("max_tokens", 1024)
        step_handle.log_step_runtime_calling_service(
            service_label="claude",
            operation="ai_prompt",
            config_summary=_config_summary_for_log(config, value=value),
        )
        clearer = getattr(claude, "clear_last_ai_prompt_trace", None)
        if callable(clearer):
            clearer()

        result = claude.prompt_completion(
            prompt=prompt,
            value=value,
            max_tokens=max_tokens,
        )
        raw_text = result or ""
        _log_claude_ai_prompt_service_trace(
            step_handle,
            claude,
            result=raw_text,
            max_tokens=max_tokens,
        )
        step_handle.log_step_runtime_received_success()

        finalized = self._finalize_value(config, raw_text)
        if finalized != raw_text:
            step_handle.log_step_runtime_transforming(
                from_preview=raw_text,
                to_preview=finalized,
            )

        usage_svc = ctx.get_service("usage_accounting")
        if usage_svc and ctx.owner_user_id:
            usage = claude.get_last_usage()
            if isinstance(usage, dict):
                await usage_svc.record_llm_tokens(
                    job_run_id=ctx.run_id,
                    owner_user_id=ctx.owner_user_id,
                    provider="anthropic",
                    prompt_tokens=usage.get("input_tokens", 0),
                    completion_tokens=usage.get("output_tokens", 0),
                    step_run_id=step_handle.step_run_id,
                    model=usage.get("model"),
                )
        return {"value": finalized}
