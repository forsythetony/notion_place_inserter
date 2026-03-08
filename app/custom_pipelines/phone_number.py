"""Custom pipeline for Phone Number: extract from place (or None if not available)."""

from app.models.schema import PropertySchema
from app.pipeline_lib.context import ContextKeys, PipelineRunContext
from app.pipeline_lib.core import Pipeline, PipelineStep
from app.pipeline_lib.logging import log_step
from app.pipeline_lib.steps.notion_format import format_value_for_notion


class ExtractPhoneStep(PipelineStep):
    """Extract phone from place. Google Places may not include it in basic fields."""

    def __init__(self, prop_name: str):
        self._prop_name = prop_name

    @property
    def step_id(self) -> str:
        return "extract_phone"

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
            if not place:
                return None
            return place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber")


class FormatPhoneStep(PipelineStep):
    """Format as Notion phone_number."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def step_id(self) -> str:
        return "format_phone"

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


class PhoneNumberPipeline(Pipeline):
    """Resolve phone from place. Returns None if not in API response."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def pipeline_id(self) -> str:
        return f"phone_{self._prop_name}"

    def steps(self) -> list[PipelineStep]:
        return [
            ExtractPhoneStep(self._prop_name),
            FormatPhoneStep(self._prop_name, self._prop_schema),
        ]
