"""Search Icons step runtime handler."""

from __future__ import annotations

from typing import Any

from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.step_runtime_base import StepRuntime


class SearchIconsHandler(StepRuntime):
    """Search icons by term (Freepik) and return first result URL."""

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
        if not isinstance(query, str):
            query = str(query).strip() if query else ""

        freepik = ctx.get_service("freepik")
        if not freepik:
            return {"image_url": None}

        url = freepik.get_first_icon_url(query.strip())
        return {"image_url": url}
