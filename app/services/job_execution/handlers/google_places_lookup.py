"""Google Places Lookup step runtime handler."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from app.env_bootstrap import is_pipeline_trace_verbose
from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle
from app.services.job_execution.step_runtime_base import StepRuntime
from app.services.pipeline_live_test.api_overrides import consume_manual_api_response

# Per-line cap for step_traces.processing (same order of magnitude as optimize_input).
_PROCESSING_PREVIEW_MAX = 2500


def _processing_preview(text: str, max_len: int = _PROCESSING_PREVIEW_MAX) -> str:
    s = text if text is not None else ""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _log_google_places_http_traces(google: Any, step_handle: StepExecutionHandle) -> None:
    """Emit URL, redacted headers, optional body, and response preview for each Places HTTP call."""
    getter = getattr(google, "get_http_traces", None)
    if not callable(getter):
        return
    traces = getter()
    if not isinstance(traces, list) or not traces:
        return
    n = len(traces)
    for i, t in enumerate(traces):
        if not isinstance(t, dict):
            continue
        op = t.get("operation", "")
        idx = f"{i + 1}/{n}"
        step_handle.log_processing(
            f"Google Places HTTP trace [{idx}] {op} {t.get('method', '')} "
            f"status={t.get('http_status')}"
        )
        step_handle.log_processing(f"URL: {t.get('url', '')}")
        step_handle.log_processing(
            "Request headers (redacted): "
            f"{_processing_preview(json.dumps(t.get('request_headers', {}), ensure_ascii=False))}"
        )
        if t.get("request_body") is not None:
            step_handle.log_processing(
                "Request body: "
                f"{_processing_preview(json.dumps(t.get('request_body'), ensure_ascii=False, default=str))}"
            )
        step_handle.log_processing(
            f"Response preview: {_processing_preview(t.get('response_body_preview', '') or '')}"
        )


class GooglePlacesLookupHandler(StepRuntime):
    """Perform Google Places search and optionally fetch details."""

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
        google = ctx.get_service("google_places")
        if google is not None and hasattr(google, "clear_http_traces"):
            google.clear_http_traces()

        manual = consume_manual_api_response(ctx, "google_places.lookup")
        if manual is not None:
            step_handle.log_processing("Using live-test manual API override (google_places.lookup).")
            step_handle.log_processing(
                f"Manual override payload (preview): {_processing_preview(json.dumps(manual, ensure_ascii=False, default=str))}"
            )
            if isinstance(manual, dict):
                return {
                    "search_response": manual.get("search_response"),
                    "selected_place": manual.get("selected_place"),
                }
            return {"search_response": None, "selected_place": None}

        if not google:
            step_handle.log_processing("Google Places service unavailable; skipping search.")
            return {"search_response": None, "selected_place": None}

        fetch_details = config.get("fetch_details_if_needed", True)
        step_handle.log_processing(
            f"Calling Google Places searchText with query preview={str(query)[:120]!r} fetch_details={fetch_details}"
        )
        trace_extra = (
            {"run_id": ctx.run_id, "step_id": step_id}
            if is_pipeline_trace_verbose()
            else None
        )
        result = google.search_places(
            str(query), return_raw_response=True, trace_extra=trace_extra
        )
        results, raw_search_response = result
        place = results[0] if results else None

        usage_svc = ctx.get_service("usage_accounting")
        if usage_svc and ctx.owner_user_id:
            await usage_svc.record_external_api_call(
                job_run_id=ctx.run_id,
                owner_user_id=ctx.owner_user_id,
                provider="google_places",
                operation="search_places",
                step_run_id=step_handle.step_run_id,
            )

        logger.bind(
            run_id=ctx.run_id,
            step_id=step_id,
            query=str(query)[:80],
        ).debug(
            "google_places_search_raw_response | raw_response={}",
            json.dumps(raw_search_response, default=str)[:500],
        )

        if place and fetch_details:
            step_handle.log_processing(
                f"Enriching place with details (place_id={place.get('id', '')[:40]!r})."
            )
            place = self._enrich_with_details_if_needed(
                google, place, trace_extra=trace_extra
            )
            usage_svc = ctx.get_service("usage_accounting")
            if usage_svc and ctx.owner_user_id and place:
                await usage_svc.record_external_api_call(
                    job_run_id=ctx.run_id,
                    owner_user_id=ctx.owner_user_id,
                    provider="google_places",
                    operation="get_place_details",
                    step_run_id=step_handle.step_run_id,
                )

        _log_google_places_http_traces(google, step_handle)

        return {
            "search_response": raw_search_response if raw_search_response else (place or {}),
            "selected_place": place,
        }

    def _enrich_with_details_if_needed(
        self,
        google: Any,
        place: dict[str, Any],
        *,
        trace_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        has_summary = bool(
            place.get("generativeSummary") or place.get("editorialSummary")
        )
        if has_summary:
            return place
        place_id = place.get("id")
        if not place_id:
            return place
        try:
            details = google.get_place_details(
                place_id, return_raw_response=True, trace_extra=trace_extra
            )
            if isinstance(details, tuple):
                details = details[0]
            if details:
                merged = dict(place)
                if details.get("generativeSummary"):
                    merged["generativeSummary"] = details["generativeSummary"]
                if details.get("editorialSummary"):
                    merged["editorialSummary"] = details["editorialSummary"]
                if details.get("addressComponents") and not merged.get("addressComponents"):
                    merged["addressComponents"] = details["addressComponents"]
                if details.get("neighborhood") is not None:
                    merged["neighborhood"] = details["neighborhood"]
                if details.get("photos") and not merged.get("photos"):
                    merged["photos"] = details["photos"]
                return merged
        except Exception:
            pass
        return place
