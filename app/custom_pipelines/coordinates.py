"""Custom pipeline for Coordinates: extract '<lat>, <lng>' from place location (no LLM)."""

from app.models.schema import PropertySchema
from app.pipeline_lib.context import PipelineRunContext
from app.pipeline_lib.core import Pipeline, PipelineStep
from app.pipeline_lib.logging import log_step
from app.pipeline_lib.steps.google_places import ExtractCoordinates
from app.pipeline_lib.steps.notion_format import format_value_for_notion


class FormatCoordinatesStep(PipelineStep):
    """Format as Notion rich_text or compatible type."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def step_id(self) -> str:
        return "format_coordinates"

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
            if current_value is None:
                return None
            formatted = format_value_for_notion(current_value, self._prop_schema)
            if formatted is not None:
                context.set_property(self._prop_name, formatted)
            return formatted


class CoordinatesPipeline(Pipeline):
    """Resolve coordinates as '<lat>, <lng>' from place location. Returns None if not in API response."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def pipeline_id(self) -> str:
        return f"coordinates_{self._prop_name}"

    def steps(self) -> list[PipelineStep]:
        return [
            ExtractCoordinates(),
            FormatCoordinatesStep(self._prop_name, self._prop_schema),
        ]
