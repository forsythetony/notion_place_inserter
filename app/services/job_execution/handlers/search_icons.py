"""Search Icons step runtime handler."""

from __future__ import annotations

from typing import Any

from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.step_runtime_base import StepRuntime
from app.services.pipeline_live_test.api_overrides import consume_manual_api_response


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

        manual = consume_manual_api_response(ctx, "freepik.search_icons")
        if manual is not None:
            ctx.log_step_processing("Using live-test manual API override (freepik.search_icons).")
            if isinstance(manual, dict):
                return {"image_url": manual.get("image_url")}
            return {"image_url": str(manual) if manual else None}

        freepik = ctx.get_service("freepik")
        if not freepik:
            ctx.log_step_processing("Freepik service unavailable; no icon URL.")
            return {"image_url": None}

        ctx.log_step_processing(f"Searching Freepik icons (query preview={query[:80]!r}).")
        url = freepik.get_first_icon_url(query.strip())
        return {"image_url": url}
