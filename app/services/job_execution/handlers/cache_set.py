"""Cache Set step runtime handler."""

from __future__ import annotations

from typing import Any

from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.step_runtime_base import StepRuntime


class CacheSetHandler(StepRuntime):
    """Store value into run-scoped shared cache."""

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        input_bindings: dict[str, Any],
        resolved_inputs: dict[str, Any],
        ctx: ExecutionContext,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        cache_key = config.get("cache_key")
        value = resolved_inputs.get("value")
        if cache_key is not None:
            ctx.run_cache[cache_key] = value
        return {}
