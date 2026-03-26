"""Search Icons step runtime handler."""

from __future__ import annotations

from typing import Any

from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle
from app.services.job_execution.step_runtime_base import StepRuntime
from app.services.pipeline_live_test.api_overrides import consume_manual_api_response


class SearchIconsHandler(StepRuntime):
    """Search icons by term (Freepik) and return first result URL."""

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
        if not isinstance(query, str):
            query = str(query).strip() if query else ""

        query_stripped = query.strip()
        if not query_stripped:
            step_handle.log_processing("Empty query; skipping icon search.")
            return {"image_url": None}

        manual = consume_manual_api_response(ctx, "freepik.search_icons")
        if manual is not None:
            step_handle.log_processing("Using live-test manual API override (freepik.search_icons).")
            if isinstance(manual, dict):
                return {"image_url": manual.get("image_url")}
            return {"image_url": str(manual) if manual else None}

        freepik = ctx.get_service("freepik")
        if not freepik:
            step_handle.log_processing("Freepik service unavailable; no icon URL.")
            return {"image_url": None}

        step_handle.log_processing(f"Searching Freepik icons (query preview={query_stripped[:80]!r}).")
        url = freepik.get_first_icon_url(query_stripped)

        usage_svc = ctx.get_service("usage_accounting")
        if usage_svc and ctx.owner_user_id:
            await usage_svc.record_external_api_call(
                job_run_id=ctx.run_id,
                owner_user_id=ctx.owner_user_id,
                provider="freepik",
                operation="search_icons",
                step_run_id=step_handle.step_run_id,
            )

        return {"image_url": url}
