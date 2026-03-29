"""AI Constrain Values (Claude) step runtime handler."""

from __future__ import annotations

import json
from typing import Any

from app.services.claude_service import ClaudeAPIError
from app.services.job_execution.binding_resolver import resolve_binding
from app.services.job_execution.runtime_types import (
    ExecutionContext,
    StepExecutionHandle,
    StepExecutionResult,
)
from app.services.job_execution.step_runtime_base import StepRuntime
from app.services.pipeline_live_test.api_overrides import consume_manual_api_response

_TEMPLATE_ID = "step_template_ai_constrain_values_claude"
_CONFIG_PREVIEW_MAX = 1200


def _preview_fragment(text: str, *, max_len: int = _CONFIG_PREVIEW_MAX) -> str:
    s = text if text is not None else ""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _input_summary_for_log(source_value: Any) -> str:
    if source_value is None:
        return "source_value=None"
    if isinstance(source_value, dict):
        return f"source_value_preview={_preview_fragment(json.dumps(source_value, default=str))!r}"
    if isinstance(source_value, list):
        return f"source_value_len={len(source_value)} preview={_preview_fragment(json.dumps(source_value, default=str))!r}"
    return f"source_value_preview={_preview_fragment(str(source_value))!r}"


def _config_summary_for_log(
    config: dict[str, Any],
    *,
    options_count: int,
    allow_suggest: bool,
    schema_property_id: str | None,
) -> str:
    max_out = config.get("max_output_values")
    eagerness = config.get("allowable_value_eagerness", 0)
    max_suggest = config.get("max_suggestible_values")
    model = config.get("model")
    return (
        f"options_count={options_count}, allow_suggest_new={allow_suggest}, "
        f"allowable_value_eagerness={eagerness!r}, max_output_values={max_out!r}, "
        f"max_suggestible_values={max_suggest!r}, model={model!r}, "
        f"schema_property_id={schema_property_id!r}"
    )


def _log_claude_multi_select_trace(
    step_handle: StepExecutionHandle,
    claude: Any,
    *,
    selected_preview: str,
) -> None:
    """Emit ClaudeService request/response lines from multi-select trace or usage fallback."""
    trace_getter = getattr(claude, "get_last_multi_select_llm_trace", None)
    trace: dict[str, Any] | None = None
    if callable(trace_getter):
        raw = trace_getter()
        if isinstance(raw, dict):
            trace = raw

    if trace:
        step_handle.log_service_provider_llm_request(
            service_label="ClaudeService",
            model=str(trace.get("model", "")),
            max_tokens=trace.get("max_tokens", 256),
            body_preview=str(trace.get("user_message", "")),
        )
        usage = trace.get("usage") if isinstance(trace.get("usage"), dict) else {}
        step_handle.log_service_provider_llm_success(
            service_label="ClaudeService",
            response_preview=str(trace.get("assistant_text", selected_preview or "")),
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
            max_tokens=256,
            body_preview="(preview unavailable; multi-select trace not recorded by service)",
        )
        step_handle.log_service_provider_llm_success(
            service_label="ClaudeService",
            response_preview=selected_preview or "",
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )
    else:
        step_handle.log_processing(
            "[ClaudeService] Completed choose_multi_select_from_context (trace metadata unavailable)."
        )


class AiConstrainValuesClaudeHandler(StepRuntime):
    """Select values from allowed list using Claude, with optional suggestion."""

    async def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        input_bindings: dict[str, Any],
        resolved_inputs: dict[str, Any],
        ctx: ExecutionContext,
        step_handle: StepExecutionHandle,
        snapshot: dict[str, Any],
    ) -> dict[str, Any] | StepExecutionResult:
        source_value = resolved_inputs.get("source_value")
        step_handle.log_processing(f"[StepRuntime] Input summary: {_input_summary_for_log(source_value)}")

        manual = consume_manual_api_response(ctx, "claude.ai_constrain_values")
        if manual is not None:
            step_handle.log_processing(
                "Using live-test manual API override (claude.ai_constrain_values)."
            )
            if isinstance(manual, dict) and "selected_values" in manual:
                sv = manual.get("selected_values") or []
                out = list(sv) if isinstance(sv, list) else [sv]
                step_handle.log_processing(
                    f"[StepRuntime] Output summary: selected_count={len(out)} values_preview={out!r}"
                )
                return {"selected_values": out}
            step_handle.log_processing("[StepRuntime] Output summary: selected_count=0 (override empty)")
            return {"selected_values": []}

        claude = ctx.get_service("claude")
        if not claude:
            msg = "Claude service not configured on execution context"
            step_handle.log_processing(
                f"[StepRuntime] step failed step_template={_TEMPLATE_ID} service=ClaudeService "
                "operation=choose_multi_select_from_context retryable=False"
            )
            return StepExecutionResult(
                outcome="failed",
                error_message=msg,
                error_detail={
                    "service": "ClaudeService",
                    "operation": "choose_multi_select_from_context",
                    "message": msg,
                    "details": {"reason": "claude_missing"},
                    "retryable": False,
                },
            )

        allowable_src = config.get("allowable_values_source") or {}
        schema_property_id: str | None = None
        if isinstance(allowable_src, dict) and "target_schema_ref" in allowable_src:
            tsr = allowable_src["target_schema_ref"]
            if isinstance(tsr, dict):
                raw_id = tsr.get("schema_property_id")
                schema_property_id = str(raw_id) if raw_id is not None else None

        options = None
        if isinstance(allowable_src, dict) and "target_schema_ref" in allowable_src:
            opts = resolve_binding(
                {"target_schema_ref": allowable_src["target_schema_ref"]},
                ctx,
                snapshot,
            )
            if isinstance(opts, list):
                options = [o.get("name", o.get("id", str(o))) for o in opts if isinstance(o, dict)]
            elif opts is not None:
                options = [str(opts)]
        if not options:
            step_handle.log_processing(
                "No allowable options from schema; returning empty selection (valid configuration gap)."
            )
            step_handle.log_processing("[StepRuntime] Output summary: selected_count=0")
            return {"selected_values": []}

        allow_suggest = bool(config.get("allowable_value_eagerness", 0) or 0)
        step_handle.log_processing(
            f"[StepRuntime] Configuration summary: {_config_summary_for_log(config, options_count=len(options), allow_suggest=allow_suggest, schema_property_id=schema_property_id)}"
        )

        candidate_context = self._build_candidate_context(source_value)
        clearer = getattr(claude, "clear_last_multi_select_trace", None)
        if callable(clearer):
            clearer()

        step_handle.log_step_runtime_calling_service(
            service_label="claude",
            operation="choose_multi_select_from_context",
            config_summary=_config_summary_for_log(
                config,
                options_count=len(options),
                allow_suggest=allow_suggest,
                schema_property_id=schema_property_id,
            ),
        )

        try:
            selected = claude.choose_multi_select_from_context(
                field_name="values",
                options=options,
                candidate_context=candidate_context,
                allow_suggest_new=allow_suggest,
            )
        except ClaudeAPIError as exc:
            step_handle.log_processing(
                f"[StepRuntime] step failed step_template={_TEMPLATE_ID} service={exc.service} "
                f"operation={exc.operation} retryable={exc.retryable}"
            )
            return StepExecutionResult(
                outcome="failed",
                error_message=str(exc),
                error_detail={
                    "service": exc.service,
                    "operation": exc.operation,
                    "message": str(exc),
                    "details": exc.details,
                    "retryable": exc.retryable,
                },
            )

        raw_preview = json.dumps(selected, default=str) if selected else "[]"
        _log_claude_multi_select_trace(step_handle, claude, selected_preview=raw_preview)
        step_handle.log_step_runtime_received_success()

        max_output = config.get("max_output_values")
        if max_output is not None and isinstance(selected, list) and len(selected) > max_output:
            selected = selected[:max_output]
            step_handle.log_processing(
                f"[StepRuntime] Truncated selected_values to max_output_values={max_output}"
            )

        out_list = list(selected or [])
        step_handle.log_processing(
            f"[StepRuntime] Output summary: selected_count={len(out_list)} values_preview={out_list!r}"
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

        return {"selected_values": out_list}

    def _build_candidate_context(self, source_value: Any) -> dict[str, Any]:
        if isinstance(source_value, dict):
            return source_value
        if isinstance(source_value, list):
            return {"values": source_value}
        return {"value": source_value}
