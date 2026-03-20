"""Optimize Input (Claude) step runtime handler."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.step_runtime_base import StepRuntime


def _find_pipeline_containing_step(snapshot: dict[str, Any], step_id: str) -> list[dict[str, Any]] | None:
    """Return the steps list of the pipeline containing step_id, or None."""
    job = snapshot.get("job") or {}
    stages = job.get("stages") or []
    for stage in stages:
        for pipeline in stage.get("pipelines") or []:
            steps = pipeline.get("steps") or []
            for step in steps:
                if step.get("id") == step_id:
                    return steps
    return None


def _find_linked_step(
    steps: list[dict[str, Any]],
    step_id: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Resolve the linked consumer step.
    Prefer config.linked_step_id; else auto-discover from input_bindings.
    """
    linked_id = config.get("linked_step_id")
    if linked_id:
        for s in steps:
            if s.get("id") == linked_id:
                return s
        logger.warning(
            "optimize_input_linked_step_not_found | step_id={} linked_step_id={}",
            step_id,
            linked_id,
        )
        return None
    target_ref = f"step.{step_id}.optimized_query"
    for s in steps:
        bindings = s.get("input_bindings") or {}
        for binding in bindings.values():
            if isinstance(binding, dict):
                ref = binding.get("signal_ref")
                if ref == target_ref or (isinstance(ref, str) and ref.startswith(target_ref)):
                    return s
    return None


class OptimizeInputClaudeHandler(StepRuntime):
    """Reshape input via Claude for downstream consumption (e.g. Google Places query)."""

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        input_bindings: dict[str, Any],
        resolved_inputs: dict[str, Any],
        ctx: ExecutionContext,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        query = resolved_inputs.get("query") or ""
        claude = ctx.get_service("claude")
        if not claude:
            return {"optimized_query": str(query).strip()}

        if not str(query).strip():
            return {"optimized_query": ""}

        query_schema = None
        if config.get("include_target_query_schema") is not False:
            steps = _find_pipeline_containing_step(snapshot, step_id)
            if steps:
                linked = _find_linked_step(steps, step_id, config)
                if linked:
                    template_id = linked.get("step_template_id")
                    if template_id:
                        step_templates = snapshot.get("step_templates") or {}
                        template_data = step_templates.get(template_id) or {}
                        query_schema = template_data.get("query_schema")

        base_prompt = config.get("prompt")
        if query_schema:
            rewritten = claude.rewrite_query_for_target(
                str(query),
                query_schema=query_schema,
                base_prompt=base_prompt,
            )
        else:
            rewritten = claude.rewrite_place_query(str(query))

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
        return {"optimized_query": rewritten or str(query).strip()}
