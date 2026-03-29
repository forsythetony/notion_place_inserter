"""Search Icons (Iconify) step runtime handler."""

from __future__ import annotations

import json
from typing import Any

from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle
from app.services.job_execution.step_runtime_base import StepRuntime
from app.services.pipeline_live_test.api_overrides import consume_manual_api_response

_PROCESSING_FULL_MAX = 100_000


def _iconify_trace_log_text(trace: dict[str, Any]) -> str:
    raw = json.dumps(trace, indent=2, default=str, ensure_ascii=False)
    if len(raw) <= _PROCESSING_FULL_MAX:
        return raw
    return raw[: _PROCESSING_FULL_MAX - 40] + "\n...(truncated)"


class SearchIconsIconifyHandler(StepRuntime):
    """Search icons via Iconify public API and return the first hit SVG URL."""

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
            step_handle.log_processing("Empty query; skipping Iconify icon search.")
            return {"image_url": None}

        manual = consume_manual_api_response(ctx, "iconify.search_icons")
        if manual is not None:
            step_handle.log_processing("Using live-test manual API override (iconify.search_icons).")
            if isinstance(manual, dict):
                return {"image_url": manual.get("image_url")}
            return {"image_url": str(manual) if manual else None}

        iconify = ctx.get_service("iconify")
        if not iconify:
            step_handle.log_processing("Iconify service unavailable; no icon URL.")
            return {"image_url": None}

        step_handle.log_processing(f"Iconify icon search query (full): {query_stripped!r}")
        url: str | None = None
        try:
            url = iconify.get_first_icon_svg_url(query_stripped)
        finally:
            trace_getter = getattr(iconify, "get_last_search_trace", None)
            if callable(trace_getter):
                tr = trace_getter()
                if isinstance(tr, dict):
                    tr = {**tr, "resolved_svg_url": url}
                    step_handle.log_processing(
                        "Iconify GET /search trace (full):\n" + _iconify_trace_log_text(tr)
                    )

        return {"image_url": url}
