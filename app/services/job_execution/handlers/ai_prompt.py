"""AI Prompt step runtime handler."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.step_runtime_base import StepRuntime


class AiPromptHandler(StepRuntime):
    """Run a configurable AI prompt on an input value; output is the model's text response."""

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        input_bindings: dict[str, Any],
        resolved_inputs: dict[str, Any],
        ctx: ExecutionContext,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        value = resolved_inputs.get("value")
        prompt = config.get("prompt", "")

        if not prompt:
            logger.warning("ai_prompt_missing_prompt | step_id={}", step_id)
            return {"value": ""}

        claude = ctx.get_service("claude")
        if not claude:
            logger.warning("ai_prompt_no_claude | step_id={}", step_id)
            return {"value": ""}

        max_tokens = config.get("max_tokens", 1024)
        result = claude.prompt_completion(
            prompt=prompt,
            value=value,
            max_tokens=max_tokens,
        )
        usage_svc = ctx.get_service("usage_accounting")
        if usage_svc and ctx.owner_user_id:
            usage = claude.get_last_usage()
            if usage:
                usage_svc.record_llm_tokens(
                    job_run_id=ctx.run_id,
                    owner_user_id=ctx.owner_user_id,
                    provider="anthropic",
                    prompt_tokens=usage.get("input_tokens", 0),
                    completion_tokens=usage.get("output_tokens", 0),
                    step_run_id=ctx.step_run_id,
                )
        return {"value": result or ""}
