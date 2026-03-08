"""Place-intake stage pipelines: query rewrite and Google Places fetch."""

import os

from app.pipeline_lib.context import ContextKeys, PipelineRunContext
from app.pipeline_lib.core import Pipeline, PipelineStep
from app.pipeline_lib.logging import log_step


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
            results = google.search_places(query)
            place = results[0] if results else None
            if place and self._fetch_details_if_needed:
                place = self._enrich_with_details_if_needed(google, place)
            context.set(ContextKeys.GOOGLE_PLACE, place)
            return place

    def _enrich_with_details_if_needed(self, google, place: dict) -> dict:
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
            details = google.get_place_details(place_id)
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
