"""ABC for executable step handlers (runtime, not data model)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle


class StepRuntime(ABC):
    """
    Runtime handler for a step template. Separate from domain StepTemplate/StepInstance.
    Orchestrator instantiates and invokes based on step_template_id from snapshot.
    """

    @abstractmethod
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
        """
        Execute the step. Returns dict of output_name -> value for downstream bindings.
        """
        ...
