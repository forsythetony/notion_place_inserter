"""AI Prompt step runtime handler."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle
from app.services.job_execution.step_runtime_base import StepRuntime
from app.services.pipeline_live_test.api_overrides import consume_manual_api_response


class AiPromptHandler(StepRuntime):
    """Run a configurable AI prompt on an input value; output is the model's text response."""

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
                return {"value": manual.get("value", "")}
            return {"value": str(manual) if manual is not None else ""}

        claude = ctx.get_service("claude")
        if not claude:
            logger.warning("ai_prompt_no_claude | step_id={}", step_id)
            return {"value": ""}

        max_tokens = config.get("max_tokens", 1024)
        step_handle.log_processing(f"Calling Claude ai_prompt (max_tokens={max_tokens}).")
        result = claude.prompt_completion(
            prompt=prompt,
            value=value,
            max_tokens=max_tokens,
        )
        usage_svc = ctx.get_service("usage_accounting")
        if usage_svc and ctx.owner_user_id:
            usage = claude.get_last_usage()
            if usage:
                await usage_svc.record_llm_tokens(
                    job_run_id=ctx.run_id,
                    owner_user_id=ctx.owner_user_id,
                    provider="anthropic",
                    prompt_tokens=usage.get("input_tokens", 0),
                    completion_tokens=usage.get("output_tokens", 0),
                    step_run_id=step_handle.step_run_id,
                    model=usage.get("model"),
                )
        return {"value": result or ""}
