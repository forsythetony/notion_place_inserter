"""Custom pipeline for Neighborhood select: infer from place or suggest new when appropriate."""

import re

from loguru import logger

from app.models.schema import PropertySchema
from app.pipeline_lib.context import ContextKeys, PipelineRunContext
from app.pipeline_lib.core import Pipeline, PipelineStep
from app.pipeline_lib.logging import bind_orchestration, log_step
from app.pipeline_lib.steps.notion_format import format_value_for_notion


class InferNeighborhoodStep(PipelineStep):
    """
    Infer neighborhood from Google place signals. Maps to existing schema option when
    possible; may suggest a new neighborhood when evidence is strong and no option matches.
    Returns None for places where neighborhood does not apply (e.g. national parks,
    landmarks in remote areas).
    """

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def step_id(self) -> str:
        return "infer_neighborhood"

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
            property_type=self._prop_schema.type,
        ):
            options = [o.name for o in (self._prop_schema.options or []) if o.name]
            place = context.get(ContextKeys.GOOGLE_PLACE)
            if not place:
                context.mark_property_omitted(
                    self._prop_name, reason="missing_google_place"
                )
                return None

            direct_match = _match_option_from_place_neighborhood(place, options)
            if direct_match:
                log = bind_orchestration(
                    run_id=context.run_id,
                    global_pipeline=context.get("_global_pipeline_id", ""),
                    stage=context.get("_current_stage_id", ""),
                    pipeline=context.get("_current_pipeline_id", ""),
                    step=self.step_id,
                    property_name=self._prop_name,
                    property_type=self._prop_schema.type,
                    direct_selected_value=direct_match,
                )
                log.info("neighborhood_option_selection_direct_match")
                return direct_match

            # Deterministic fast path: strong Google signals (neighborhood, sublocality_level_1)
            # create new value directly when no existing option matches.
            strong_signal_types = ("neighborhood", "sublocality_level_1")
            signal_type = place.get("neighborhood_signal_type")
            raw_neighborhood = (place.get("neighborhood") or "").strip()
            if (
                signal_type in strong_signal_types
                and raw_neighborhood
                and _passes_directional_geo_guard(raw_neighborhood, place)
            ):
                new_value = raw_neighborhood.title()
                log = bind_orchestration(
                    run_id=context.run_id,
                    global_pipeline=context.get("_global_pipeline_id", ""),
                    stage=context.get("_current_stage_id", ""),
                    pipeline=context.get("_current_pipeline_id", ""),
                    step=self.step_id,
                    property_name=self._prop_name,
                    property_type=self._prop_schema.type,
                    deterministic_signal_type=signal_type,
                    deterministic_selected_value=new_value,
                )
                log.info("neighborhood_option_selection_deterministic_strong_signal")
                msg = f"Value not found for {self._prop_name}, creating new neighborhood {new_value}"
                logger.info(msg)
                return new_value

            candidate_context = {
                "neighborhood": place.get("neighborhood"),
                "formattedAddress": place.get("formattedAddress"),
                "displayName": place.get("displayName"),
                "primaryType": place.get("primaryType"),
                "types": place.get("types", []),
                "generativeSummary": place.get("generativeSummary"),
                "editorialSummary": place.get("editorialSummary"),
                "latitude": place.get("latitude"),
                "longitude": place.get("longitude"),
                "addressComponents": place.get("addressComponents", []),
            }

            google_signals = place.get("google_neighborhood_signals") or []
            address_components = place.get("addressComponents") or []
            debug_log = bind_orchestration(
                run_id=context.run_id,
                global_pipeline=context.get("_global_pipeline_id", ""),
                stage=context.get("_current_stage_id", ""),
                pipeline=context.get("_current_pipeline_id", ""),
                step=self.step_id,
                property_name=self._prop_name,
                property_type=self._prop_schema.type,
            )
            if not google_signals:
                debug_log.bind(
                    place_id=place.get("id"),
                    address_component_count=len(address_components),
                ).info("neighborhood_no_google_sublocality_signals")
            else:
                debug_log.bind(google_neighborhood_signals=google_signals).info(
                    "neighborhood_google_signals_received"
                )
            address_components_subset = [
                {
                    "text": c.get("longText") or c.get("shortText") or "",
                    "types": c.get("types", []),
                }
                for c in address_components
                if isinstance(c, dict)
                and (
                    "neighborhood" in (c.get("types") or [])
                    or "sublocality" in (c.get("types") or [])
                    or any(t.startswith("sublocality_level_") for t in (c.get("types") or []))
                    or "administrative_area_level_3" in (c.get("types") or [])
                    or "locality" in (c.get("types") or [])
                )
            ]

            log = bind_orchestration(
                run_id=context.run_id,
                global_pipeline=context.get("_global_pipeline_id", ""),
                stage=context.get("_current_stage_id", ""),
                pipeline=context.get("_current_pipeline_id", ""),
                step=self.step_id,
                property_name=self._prop_name,
                property_type=self._prop_schema.type,
                options=options,
                candidate_context=candidate_context,
                google_neighborhood_signals=google_signals,
                neighborhood_options=options,
                address_components_neighborhood_subset=address_components_subset,
            )
            log.info("neighborhood_option_selection_request")

            claude = context.get("_claude_service")
            if not claude:
                context.mark_property_omitted(
                    self._prop_name, reason="missing_claude_service"
                )
                return None

            result = claude.choose_option_with_suggest_from_context(
                field_name=self._prop_name,
                options=options,
                candidate_context=candidate_context,
                allow_suggest_new=True,
            )

            if result.value is None:
                log.info("neighborhood_option_selection_no_value")
                context.mark_property_omitted(self._prop_name, reason="no_value")
                return None

            if not _passes_directional_geo_guard(result.value, place):
                log.bind(
                    claude_selected_value=result.value,
                    neighborhood=place.get("neighborhood"),
                    formatted_address=place.get("formattedAddress"),
                    latitude=place.get("latitude"),
                    longitude=place.get("longitude"),
                ).warning("neighborhood_option_selection_rejected_directional_conflict")
                context.mark_property_omitted(
                    self._prop_name, reason="directional_conflict"
                )
                return None

            if result.is_new:
                msg = f"Value not found for {self._prop_name}, creating new neighborhood {result.value}"
                logger.info(msg)

            log.bind(
                claude_selected_value=result.value,
                is_new_neighborhood=result.is_new,
            ).info("neighborhood_option_selection_result")
            return result.value


class FormatNeighborhoodStep(PipelineStep):
    """Format as Notion select."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def step_id(self) -> str:
        return "format_neighborhood"

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
            property_type=self._prop_schema.type,
        ):
            formatted = format_value_for_notion(current_value, self._prop_schema)
            if formatted is not None:
                context.set_property(self._prop_name, formatted)
            return formatted


class NeighborhoodPipeline(Pipeline):
    """Resolve neighborhood select from place context."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def pipeline_id(self) -> str:
        return f"neighborhood_{self._prop_name}"

    def steps(self) -> list[PipelineStep]:
        return [
            InferNeighborhoodStep(self._prop_name, self._prop_schema),
            FormatNeighborhoodStep(self._prop_name, self._prop_schema),
        ]


_DIRECTION_TOKEN_PATTERN = re.compile(
    r"\b(ne|nw|se|sw|north(?:east|west)?|south(?:east|west)?|east|west)\b",
    re.IGNORECASE,
)

_DIRECTION_NORMALIZATION = {
    "ne": "northeast",
    "nw": "northwest",
    "se": "southeast",
    "sw": "southwest",
}

_AXIS_SIGNS: dict[str, tuple[int | None, int | None]] = {
    "north": (1, None),
    "south": (-1, None),
    "east": (None, 1),
    "west": (None, -1),
    "northeast": (1, 1),
    "northwest": (1, -1),
    "southeast": (-1, 1),
    "southwest": (-1, -1),
}


def _normalize_direction(token: str) -> str:
    lowered = token.strip().lower()
    return _DIRECTION_NORMALIZATION.get(lowered, lowered)


def _extract_direction_tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    matches = _DIRECTION_TOKEN_PATTERN.findall(text)
    return {_normalize_direction(m) for m in matches}


def _directional_conflict(selected_tokens: set[str], context_tokens: set[str]) -> bool:
    for selected in selected_tokens:
        sel_lat, sel_lon = _AXIS_SIGNS.get(selected, (None, None))
        for ctx in context_tokens:
            ctx_lat, ctx_lon = _AXIS_SIGNS.get(ctx, (None, None))
            if sel_lat is not None and ctx_lat is not None and sel_lat != ctx_lat:
                return True
            if sel_lon is not None and ctx_lon is not None and sel_lon != ctx_lon:
                return True
    return False


def _passes_directional_geo_guard(selected_value: str, place: dict) -> bool:
    selected_tokens = _extract_direction_tokens(selected_value)
    if not selected_tokens:
        return True

    address_components = place.get("addressComponents") or []
    component_text = " ".join(
        (comp.get("longText") or comp.get("shortText") or "")
        for comp in address_components
        if isinstance(comp, dict)
    )
    context_blob = " ".join(
        [
            str(place.get("neighborhood") or ""),
            str(place.get("formattedAddress") or ""),
            str(place.get("displayName") or ""),
            component_text,
        ]
    )
    context_tokens = _extract_direction_tokens(context_blob)
    if not context_tokens:
        return True
    return not _directional_conflict(selected_tokens, context_tokens)


def _match_option_from_place_neighborhood(place: dict, options: list[str]) -> str | None:
    raw_neighborhood = str(place.get("neighborhood") or "").strip()
    if not raw_neighborhood:
        return None
    neighborhood_lower = raw_neighborhood.lower()
    for option in options:
        option_lower = option.lower()
        if option_lower == neighborhood_lower:
            return option
        if neighborhood_lower in option_lower or option_lower in neighborhood_lower:
            return option
    return None
