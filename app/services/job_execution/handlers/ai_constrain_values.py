"""AI Constrain Values (Claude) step runtime handler."""

from __future__ import annotations

from typing import Any

from app.services.job_execution.binding_resolver import resolve_binding
from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle
from app.services.job_execution.step_runtime_base import StepRuntime
from app.services.pipeline_live_test.api_overrides import consume_manual_api_response


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
    ) -> dict[str, Any]:
        source_value = resolved_inputs.get("source_value")
        manual = consume_manual_api_response(ctx, "claude.ai_constrain_values")
        if manual is not None:
            step_handle.log_processing("Using live-test manual API override (claude.ai_constrain_values).")
            if isinstance(manual, dict) and "selected_values" in manual:
                sv = manual.get("selected_values") or []
                return {"selected_values": list(sv) if isinstance(sv, list) else [sv]}
            return {"selected_values": []}

        claude = ctx.get_service("claude")
        if not claude:
            step_handle.log_processing("Claude unavailable; no selected values.")
            return {"selected_values": []}

        allowable_src = config.get("allowable_values_source") or {}
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
            step_handle.log_processing("No allowable options from schema; returning empty selection.")
            return {"selected_values": []}

        allow_suggest = bool(config.get("allowable_value_eagerness", 0) or 0)
        step_handle.log_processing(
            f"Calling Claude to constrain values (options_count={len(options)}, allow_suggest={allow_suggest})."
        )
        candidate_context = self._build_candidate_context(source_value)
        selected = claude.choose_multi_select_from_context(
            field_name="values",
            options=options,
            candidate_context=candidate_context,
            allow_suggest_new=allow_suggest,
        )
        max_output = config.get("max_output_values")
        if max_output is not None and isinstance(selected, list) and len(selected) > max_output:
            selected = selected[:max_output]
        return {"selected_values": selected or []}

    def _build_candidate_context(self, source_value: Any) -> dict[str, Any]:
        if isinstance(source_value, dict):
            return source_value
        if isinstance(source_value, list):
            return {"values": source_value}
        return {"value": source_value}
