"""Registry mapping step_template_id to StepRuntime handler factory."""

from __future__ import annotations

from typing import Callable, Type

from app.services.job_execution.step_runtime_base import StepRuntime


class StepRuntimeRegistry:
    """Maps step_template_id to runtime handler class or factory."""

    def __init__(self) -> None:
        self._handlers: dict[str, type[StepRuntime] | Callable[[], StepRuntime]] = {}

    def register(
        self,
        step_template_id: str,
        handler: type[StepRuntime] | Callable[[], StepRuntime],
    ) -> None:
        self._handlers[step_template_id] = handler

    def get(self, step_template_id: str) -> StepRuntime | None:
        h = self._handlers.get(step_template_id)
        if h is None:
            return None
        if isinstance(h, type):
            return h()
        return h()

    def __contains__(self, step_template_id: str) -> bool:
        return step_template_id in self._handlers
