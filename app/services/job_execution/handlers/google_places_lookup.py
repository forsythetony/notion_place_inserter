"""Google Places Lookup step runtime handler."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.step_runtime_base import StepRuntime


class GooglePlacesLookupHandler(StepRuntime):
    """Perform Google Places search and optionally fetch details."""

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
        google = ctx.get_service("google_places")
        if not google:
            return {"search_response": None, "selected_place": None}

        fetch_details = config.get("fetch_details_if_needed", True)
        result = google.search_places(str(query), return_raw_response=True)
        results, raw_search_response = result
        place = results[0] if results else None

        usage_svc = ctx.get_service("usage_accounting")
        if usage_svc and ctx.owner_user_id:
            usage_svc.record_external_api_call(
                job_run_id=ctx.run_id,
                owner_user_id=ctx.owner_user_id,
                provider="google_places",
                operation="search_places",
                step_run_id=ctx.step_run_id,
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
            place = self._enrich_with_details_if_needed(google, place)
            usage_svc = ctx.get_service("usage_accounting")
            if usage_svc and ctx.owner_user_id and place:
                usage_svc.record_external_api_call(
                    job_run_id=ctx.run_id,
                    owner_user_id=ctx.owner_user_id,
                    provider="google_places",
                    operation="get_place_details",
                    step_run_id=ctx.step_run_id,
                )

        return {
            "search_response": raw_search_response if raw_search_response else (place or {}),
            "selected_place": place,
        }

    def _enrich_with_details_if_needed(
        self,
        google: Any,
        place: dict[str, Any],
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
            details = google.get_place_details(place_id, return_raw_response=True)
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
