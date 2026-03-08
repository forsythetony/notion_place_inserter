"""Pipeline steps for resolving Places-to-Locations relation."""

import os

from loguru import logger

from app.models.location import LocationCandidate, LocationResolution
from app.pipeline_lib.context import ContextKeys, PipelineRunContext
from app.pipeline_lib.core import PipelineStep
from app.pipeline_lib.logging import log_step


def _extract_from_address_components(components: list[dict] | None) -> tuple[str | None, str | None, str | None]:
    """
    Extract locality (city), state/region, country from addressComponents.
    Returns (locality, state_or_region, country).
    """
    if not components:
        return (None, None, None)
    locality = None
    state = None
    country = None
    for comp in components:
        types_list = comp.get("types") or []
        if not isinstance(types_list, list):
            continue
        text = (comp.get("longText") or comp.get("shortText") or "").strip()
        if not text:
            continue
        if "locality" in types_list:
            locality = text
        elif "administrative_area_level_1" in types_list:
            state = text
        elif "country" in types_list:
            country = text
    return (locality, state, country)


class BuildLocationCandidateStep(PipelineStep):
    """Build LocationCandidate from GOOGLE_PLACE and/or query context."""

    def __init__(self, prop_name: str):
        self._prop_name = prop_name

    @property
    def step_id(self) -> str:
        return "build_location_candidate"

    def execute(
        self, context: PipelineRunContext, current_value: object
    ) -> object:
        with log_step(
            context.run_id,
            context.get("_global_pipeline_id", ""),
            context.get("_current_stage_id", ""),
            context.get("_current_pipeline_id", ""),
            self.step_id,
            step_name=self.name,
            step_description=self.description or None,
            property_name=self._prop_name,
        ):
            place = context.get(ContextKeys.GOOGLE_PLACE)
            raw_query = context.get(ContextKeys.RAW_QUERY) or ""

            display_name = ""
            state_or_region = None
            country = None
            google_place_id = None

            if place:
                locality, state, c = _extract_from_address_components(
                    place.get("addressComponents")
                )
                display_name = locality or place.get("displayName") or ""
                state_or_region = state
                country = c
                google_place_id = place.get("id")

            if not display_name and raw_query:
                display_name = raw_query.strip()

            if not display_name:
                return None

            candidate = LocationCandidate(
                display_name=display_name,
                state_or_region=state_or_region,
                country=country,
                google_place_id=google_place_id,
            )
            context.set("_location_candidate", candidate)
            return candidate


class ResolveLocationRelationStep(PipelineStep):
    """Call LocationsService.resolve_or_create and store resolution in context."""

    def __init__(self, prop_name: str):
        self._prop_name = prop_name

    @property
    def step_id(self) -> str:
        return "resolve_location_relation"

    def execute(
        self, context: PipelineRunContext, current_value: object
    ) -> object:
        with log_step(
            context.run_id,
            context.get("_global_pipeline_id", ""),
            context.get("_current_stage_id", ""),
            context.get("_current_pipeline_id", ""),
            self.step_id,
            step_name=self.name,
            step_description=self.description or None,
            property_name=self._prop_name,
        ):
            candidate: LocationCandidate | None = current_value
            if not candidate:
                return None

            location_service = context.get("_location_service")
            if not location_service:
                logger.warning(
                    "location_relation_resolution_skipped",
                    reason="no_location_service",
                    property_name=self._prop_name,
                )
                return None

            try:
                logger.bind(
                    run_id=context.run_id,
                    property_name=self._prop_name,
                    candidate_name=candidate.display_name,
                ).info("location_relation_resolution_started")

                dry_run = context.get("_dry_run", False)
                google_place = context.get(ContextKeys.GOOGLE_PLACE)
                resolution = location_service.resolve_or_create(
                    candidate,
                    dry_run=dry_run,
                    google_place=google_place,
                )
                context.set("_location_resolution", resolution)
                return resolution
            except Exception as e:
                logger.bind(
                    run_id=context.run_id,
                    property_name=self._prop_name,
                    candidate_name=candidate.display_name,
                    error=str(e),
                ).error("location_relation_resolution_failed")
                if os.environ.get("LOCATION_RELATION_REQUIRED", "0") == "1":
                    raise
                return None


class FormatLocationRelationForNotionStep(PipelineStep):
    """Output Notion relation payload: {\"relation\": [{\"id\": page_id}]}."""

    def __init__(self, prop_name: str):
        self._prop_name = prop_name

    @property
    def step_id(self) -> str:
        return "format_location_relation_for_notion"

    def execute(
        self, context: PipelineRunContext, current_value: object
    ) -> object:
        with log_step(
            context.run_id,
            context.get("_global_pipeline_id", ""),
            context.get("_current_stage_id", ""),
            context.get("_current_pipeline_id", ""),
            self.step_id,
            step_name=self.name,
            step_description=self.description or None,
            property_name=self._prop_name,
        ):
            resolution: LocationResolution | None = current_value
            if not resolution:
                return None

            formatted = {"relation": [{"id": resolution.location_page_id}]}
            context.set_property(self._prop_name, formatted)
            return formatted
