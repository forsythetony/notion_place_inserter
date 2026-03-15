"""Cache Get step runtime handler."""

from __future__ import annotations

from typing import Any

from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.step_runtime_base import StepRuntime


class CacheGetHandler(StepRuntime):
    """Retrieve value from run-scoped shared cache."""

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
        value = ctx.run_cache.get(cache_key) if cache_key else None
        return {"value": value}
