"""Place-intake stage pipelines: query rewrite and Google Places fetch."""

import json
import os

from app.pipeline_lib.context import ContextKeys, PipelineRunContext
from app.pipeline_lib.core import Pipeline, PipelineStep
from app.pipeline_lib.logging import bind_orchestration, log_step


class RewriteQueryWithClaudeStep(PipelineStep):
    """Use Claude to transform raw query into a stronger Google Places request."""

    @property
    def step_id(self) -> str:
        return "rewrite_query_with_claude"

    def execute(
        self, context: PipelineRunContext, current_value: object
    ) -> object:
        run_id = context.run_id
        gp_id = context.get("_global_pipeline_id", "")
        stage_id = context.get("_current_stage_id", "")
        pipeline_id = context.get("_current_pipeline_id", "")

        with log_step(
            run_id, gp_id, stage_id, pipeline_id, self.step_id,
            step_name=self.name,
            step_description=self.description or None,
        ):
            raw_query = context.get(ContextKeys.RAW_QUERY, "")
            claude = context.get("_claude_service")
            if not claude:
                context.set(ContextKeys.REWRITTEN_QUERY, raw_query)
                return raw_query
            rewritten = claude.rewrite_place_query(raw_query)
            context.set(ContextKeys.REWRITTEN_QUERY, rewritten)
            return rewritten


class GooglePlacesToCacheStep(PipelineStep):
    """Execute Google Places search and store result in context.
    Optionally fetches place details when search result lacks narrative summary fields.
    """

    def __init__(self, fetch_details_if_needed: bool = True):
        self._fetch_details_if_needed = fetch_details_if_needed

    @property
    def step_id(self) -> str:
        return "google_places_to_cache"

    def execute(
        self, context: PipelineRunContext, current_value: object
    ) -> object:
        run_id = context.run_id
        gp_id = context.get("_global_pipeline_id", "")
        stage_id = context.get("_current_stage_id", "")
        pipeline_id = context.get("_current_pipeline_id", "")

        with log_step(
            run_id, gp_id, stage_id, pipeline_id, self.step_id,
            step_name=self.name,
            step_description=self.description or None,
        ):
            query = context.get(ContextKeys.REWRITTEN_QUERY) or context.get(
                ContextKeys.RAW_QUERY, ""
            )
            google = context.get("_google_places_service")
            if not google:
                return None
            result = google.search_places(query, return_raw_response=True)
            results, raw_search_response = result
            place = results[0] if results else None
            bound = bind_orchestration(
                run_id=run_id,
                global_pipeline=gp_id,
                stage=stage_id,
                pipeline=pipeline_id,
                step=self.step_id,
                step_name=self.name,
            )
            bound.debug(
                "google_places_search_raw_response | raw_response={}",
                json.dumps(raw_search_response, default=str),
            )
            if place and self._fetch_details_if_needed:
                place = self._enrich_with_details_if_needed(
                    google, place, bound, run_id, gp_id, stage_id, pipeline_id
                )
            context.set(ContextKeys.GOOGLE_PLACE, place)
            return place

    def _enrich_with_details_if_needed(
        self,
        google,
        place: dict,
        bound_logger=None,
        run_id: str = "",
        gp_id: str = "",
        stage_id: str = "",
        pipeline_id: str = "",
    ) -> dict:
        """Fetch place details when search result lacks narrative summary fields."""
        has_summary = bool(
            place.get("generativeSummary") or place.get("editorialSummary")
        )
        if has_summary:
            return place
        place_id = place.get("id")
        if not place_id:
            return place
        try:
            result = google.get_place_details(place_id, return_raw_response=True)
            details, raw_details_response = result
            if bound_logger and raw_details_response is not None:
                bound_logger.debug(
                    "google_places_details_raw_response | raw_response={}",
                    json.dumps(raw_details_response, default=str),
                )
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
                if details.get("neighborhood_signal_type") is not None:
                    merged["neighborhood_signal_type"] = details["neighborhood_signal_type"]
                if details.get("google_neighborhood_signals") is not None:
                    merged["google_neighborhood_signals"] = details["google_neighborhood_signals"]
                if details.get("photos") and not merged.get("photos"):
                    merged["photos"] = details["photos"]
                return merged
        except Exception:
            pass
        return place


class QueryToGoogleCachePipeline(Pipeline):
    """Pipeline: rewrite query with Claude, then fetch from Google Places."""

    @property
    def pipeline_id(self) -> str:
        return "query_to_google_cache"

    def steps(self) -> list[PipelineStep]:
        fetch_details = os.environ.get("GOOGLE_PLACE_DETAILS_FETCH", "1") != "0"
        return [
            RewriteQueryWithClaudeStep(),
            GooglePlacesToCacheStep(fetch_details_if_needed=fetch_details),
        ]
