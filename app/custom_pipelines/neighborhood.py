"""Custom pipeline for Neighborhood select: infer from place or suggest new when appropriate."""

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
                return None

            candidate_context = {
                "neighborhood": place.get("neighborhood"),
                "formattedAddress": place.get("formattedAddress"),
                "displayName": place.get("displayName"),
                "primaryType": place.get("primaryType"),
                "types": place.get("types", []),
                "generativeSummary": place.get("generativeSummary"),
                "editorialSummary": place.get("editorialSummary"),
            }

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
            )
            log.info("neighborhood_option_selection_request")

            claude = context.get("_claude_service")
            if not claude:
                return None

            result = claude.choose_option_with_suggest_from_context(
                field_name=self._prop_name,
                options=options,
                candidate_context=candidate_context,
                allow_suggest_new=True,
            )

            if result.value is None:
                log.info("neighborhood_option_selection_no_value")
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
