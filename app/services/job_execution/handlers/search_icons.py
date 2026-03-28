"""Search Icons step runtime handler."""

from __future__ import annotations

import json
from typing import Any

from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle
from app.services.job_execution.step_runtime_base import StepRuntime
from app.services.pipeline_live_test.api_overrides import consume_manual_api_response

# Match optimize_input: cap huge JSON in step_runs.processing_log.
_PROCESSING_FULL_MAX = 100_000


def _freepik_trace_log_text(trace: dict[str, Any]) -> str:
    raw = json.dumps(trace, indent=2, default=str, ensure_ascii=False)
    if len(raw) <= _PROCESSING_FULL_MAX:
        return raw
    return raw[: _PROCESSING_FULL_MAX - 40] + "\n...(truncated)"


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

        step_handle.log_processing(f"Freepik icon search query (full): {query_stripped!r}")
        url: str | None = None
        try:
            url = freepik.get_first_icon_url(query_stripped)
        finally:
            trace_getter = getattr(freepik, "get_last_search_trace", None)
            if callable(trace_getter):
                tr = trace_getter()
                if isinstance(tr, dict):
                    tr = {**tr, "resolved_thumbnail_url": url}
                    step_handle.log_processing(
                        "Freepik GET /v1/icons trace (full):\n" + _freepik_trace_log_text(tr)
                    )

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
