"""Default/fallback property pipeline: AI infer + format for Notion type."""

from app.models.schema import PropertySchema
from app.pipeline_lib.context import ContextKeys, PipelineRunContext
from app.pipeline_lib.core import Pipeline, PipelineStep
from app.pipeline_lib.logging import log_step


SKIP_TYPES = {"relation", "formula", "created_time", "place", "rollup"}


class InferValueWithAI(PipelineStep):
    """Use Claude to infer a property value from gathered research context."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def step_id(self) -> str:
        return "infer_value_with_ai"

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
            property_name=self._prop_name,
            property_type=self._prop_schema.type,
        ):
            claude = context.get("_claude_service")
            if not claude:
                return None
            snapshot = context.snapshot()
            inferred = claude.infer_property_value(
                prop_name=self._prop_name,
                prop_type=self._prop_schema.type,
                options=[o.name for o in (self._prop_schema.options or [])],
                research_snapshot=snapshot,
            )
            return inferred


class FormatForNotionType(PipelineStep):
    """Format an inferred value into Notion API property format."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def step_id(self) -> str:
        return "format_for_notion_type"

    def execute(
        self, context: PipelineRunContext, current_value: object
    ) -> object:
        from app.pipeline_lib.steps.notion_format import format_value_for_notion

        run_id = context.run_id
        gp_id = context.get("_global_pipeline_id", "")
        stage_id = context.get("_current_stage_id", "")
        pipeline_id = context.get("_current_pipeline_id", "")

        with log_step(
            run_id, gp_id, stage_id, pipeline_id, self.step_id,
            step_name=self.name,
            step_description=self.description or None,
            property_name=self._prop_name,
            property_type=self._prop_schema.type,
        ):
            if current_value is None:
                return None
            formatted = format_value_for_notion(
                current_value, self._prop_schema
            )
            if formatted is not None:
                context.set_property(self._prop_name, formatted)
            return formatted


class DefaultPipeline(Pipeline):
    """
    Fallback pipeline for properties without a custom implementation.
    Infers value with AI, then formats for Notion type.
    """

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def pipeline_id(self) -> str:
        return f"default_{self._prop_name}"

    def steps(self) -> list[PipelineStep]:
        return [
            InferValueWithAI(self._prop_name, self._prop_schema),
            FormatForNotionType(self._prop_name, self._prop_schema),
        ]
