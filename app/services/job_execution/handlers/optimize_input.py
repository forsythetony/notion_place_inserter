"""Optimize Input (Claude) step runtime handler."""

from __future__ import annotations

from typing import Any

from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.step_runtime_base import StepRuntime


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

        prompt = config.get("prompt", "Rewrite this input into an optimized search query.")
        # TODO: include_target_query_schema + linked_step_id for schema injection
        if not str(query).strip():
            return {"optimized_query": ""}

        rewritten = claude.rewrite_place_query(str(query))
        return {"optimized_query": rewritten or str(query).strip()}
