"""Custom pipeline for properties that always resolve to a fixed constant value."""

from app.models.schema import PropertySchema
from app.pipeline_lib.context import PipelineRunContext
from app.pipeline_lib.core import Pipeline, PipelineStep
from app.pipeline_lib.logging import log_step
from app.pipeline_lib.steps.notion_format import format_value_for_notion


class ConstantValueStep(PipelineStep):
    """Set property to a constant value. Ignores incoming current_value."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema, constant_value: str):
        self._prop_name = prop_name
        self._prop_schema = prop_schema
        self._constant_value = constant_value

    @property
    def step_id(self) -> str:
        return "set_constant_value"

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
            formatted = format_value_for_notion(self._constant_value, self._prop_schema)
            if formatted is not None:
                context.set_property(self._prop_name, formatted)
            return formatted


class ConstantValuePipeline(Pipeline):
    """Resolve property to a fixed constant value. Used for fields like Source."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema, constant_value: str):
        self._prop_name = prop_name
        self._prop_schema = prop_schema
        self._constant_value = constant_value

    @property
    def pipeline_id(self) -> str:
        return f"constant_value_{self._prop_name}"

    def steps(self) -> list[PipelineStep]:
        return [
            ConstantValueStep(
                self._prop_name, self._prop_schema, self._constant_value
            )
        ]


class SourcePipeline(ConstantValuePipeline):
    """Source property always resolves to 'Notion Place Inserter'."""

    SOURCE_VALUE = "Notion Place Inserter"

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        super().__init__(prop_name, prop_schema, self.SOURCE_VALUE)
