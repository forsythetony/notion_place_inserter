"""Data Transform step runtime handler."""

from __future__ import annotations

from typing import Any

import jmespath
from jmespath.exceptions import JMESPathError

from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle
from app.services.job_execution.step_runtime_base import StepRuntime


class DataTransformHandler(StepRuntime):
    """Deterministic transform over step input using a JMESPath expression."""

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
        expression = config.get("expression", "")
        fallback_value = config.get("fallback_value")

        if not expression or not isinstance(expression, str):
            step_handle.log_processing("Data transform missing expression; using fallback.")
            transformed = fallback_value
        else:
            step_handle.log_processing(
                f"Data transform evaluate expression={expression!r}."
            )
            try:
                extracted = jmespath.search(expression, value)
            except JMESPathError as exc:
                step_handle.log_processing(
                    f"Data transform invalid expression={expression!r}; using fallback. error={exc}"
                )
                extracted = None
            transformed = extracted if extracted is not None else fallback_value

        return {"transformed_value": transformed}
