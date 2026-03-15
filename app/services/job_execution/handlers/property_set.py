"""Property Set step runtime handler."""

from __future__ import annotations

from typing import Any

from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.step_runtime_base import StepRuntime


class PropertySetHandler(StepRuntime):
    """Write value to target schema property (terminal step)."""

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        input_bindings: dict[str, Any],
        resolved_inputs: dict[str, Any],
        ctx: ExecutionContext,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        schema_property_id = config.get("schema_property_id")
        value = resolved_inputs.get("value")
        if schema_property_id is not None:
            ctx.set_property(schema_property_id, value)
        return {}
