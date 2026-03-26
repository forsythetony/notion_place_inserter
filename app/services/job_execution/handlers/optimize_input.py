"""Optimize Input (Claude) step runtime handler."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.env_bootstrap import is_pipeline_trace_verbose
from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle
from app.services.job_execution.step_runtime_base import StepRuntime
from app.services.pipeline_live_test.api_overrides import consume_manual_api_response

# Per-line cap for step_traces.processing (aligned with pipeline log preview size).
_PROCESSING_PREVIEW_MAX = 2500


def _processing_preview(text: str, max_len: int = _PROCESSING_PREVIEW_MAX) -> str:
    s = text if text is not None else ""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


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
        query = resolved_inputs.get("query") or ""
        claude = ctx.get_service("claude")
        if claude is not None and hasattr(claude, "clear_last_optimize_input_trace"):
            claude.clear_last_optimize_input_trace()

        manual = consume_manual_api_response(ctx, "claude.optimize_input")
        if manual is not None:
            step_handle.log_processing("Using live-test manual API override (claude.optimize_input).")
            step_handle.log_processing(
                f"Manual override payload (preview): {_processing_preview(str(manual))}"
            )
            if isinstance(manual, dict) and "optimized_query" in manual:
                return {"optimized_query": str(manual["optimized_query"]).strip()}
            return {"optimized_query": str(manual).strip() if manual is not None else ""}

        if not claude:
            step_handle.log_processing("Claude unavailable; passing query through unchanged.")
            return {"optimized_query": str(query).strip()}

        if not str(query).strip():
            step_handle.log_processing("Empty query; skipping optimization.")
            return {"optimized_query": ""}

        query_schema = None
        linked_template_id: str | None = None
        if config.get("include_target_query_schema") is not False:
            steps = _find_pipeline_containing_step(snapshot, step_id)
            if steps:
                linked = _find_linked_step(steps, step_id, config)
                if linked:
                    tid = linked.get("step_template_id")
                    if tid:
                        linked_template_id = str(tid)
                        step_templates = snapshot.get("step_templates") or {}
                        template_data = step_templates.get(linked_template_id) or {}
                        query_schema = template_data.get("query_schema")

        base_prompt = config.get("prompt")
        mode = "target_schema" if query_schema else "place_query_fallback"
        step_handle.log_processing(
            f"Calling Claude optimize_input (mode={mode}, linked_template_id={linked_template_id!r})."
        )
        if is_pipeline_trace_verbose():
            desc = (query_schema or {}).get("description", "") if query_schema else ""
            hints = query_schema.get("hints") if query_schema else None
            logger.bind(run_id=ctx.run_id, step_id=step_id, event="pipeline_trace").debug(
                "pipeline_trace | optimize_input | before_claude | raw_query={} | mode={} | "
                "linked_step_template_id={} | query_schema_description={} | "
                "query_schema_hints_count={} | base_prompt_present={}",
                str(query),
                mode,
                linked_template_id,
                (desc or "")[:1500],
                len(hints) if isinstance(hints, list) else 0,
                bool(
                    base_prompt and str(base_prompt).strip()
                    if base_prompt is not None
                    else False
                ),
            )
        if query_schema:
            rewritten = claude.rewrite_query_for_target(
                str(query),
                query_schema=query_schema,
                base_prompt=base_prompt,
            )
        else:
            rewritten = claude.rewrite_place_query(str(query))

        trace: dict[str, Any] | None = None
        getter = getattr(claude, "get_last_optimize_input_llm_trace", None)
        if callable(getter):
            raw = getter()
            if isinstance(raw, dict):
                trace = raw
        if trace:
            step_handle.log_processing(
                f"Claude API model={trace.get('model', '')} (optimize_input)"
            )
            step_handle.log_processing(
                f"Claude system prompt (preview): {_processing_preview(str(trace.get('system_prompt', '')), 2000)}"
            )
            step_handle.log_processing(
                f"Claude user message (preview): {_processing_preview(str(trace.get('user_message', '')), 2000)}"
            )
            step_handle.log_processing(
                f"Claude assistant text (preview): {_processing_preview(str(trace.get('assistant_text', '')), 2000)}"
            )
        else:
            step_handle.log_processing("Claude optimize_input completed.")
        if is_pipeline_trace_verbose():
            logger.bind(run_id=ctx.run_id, step_id=step_id, event="pipeline_trace").debug(
                "pipeline_trace | optimize_input | after_claude | optimized_query={}",
                (rewritten or str(query).strip())[:8000],
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
        return {"optimized_query": rewritten or str(query).strip()}
