"""Custom pipeline for Tags multi_select: infer from place context using Claude."""

from app.models.schema import PropertySchema
from app.pipeline_lib.context import ContextKeys, PipelineRunContext
from app.pipeline_lib.core import Pipeline, PipelineStep
from app.pipeline_lib.logging import bind_orchestration, log_step
from app.pipeline_lib.steps.notion_format import format_value_for_notion


class InferTagsStep(PipelineStep):
    """Infer tags from Google place signals using existing schema options only."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def step_id(self) -> str:
        return "infer_tags"

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
            if not place or not options:
                return None

            candidate_context = {
                "primaryType": place.get("primaryType"),
                "types": place.get("types", []),
                "displayName": place.get("displayName"),
                "editorialSummary": place.get("editorialSummary"),
                "formattedAddress": place.get("formattedAddress"),
                "rating": place.get("rating"),
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
            log.info("tags_multi_select_request")

            claude = context.get("_claude_service")
            if not claude:
                return None

            selected = claude.choose_multi_select_from_context(
                field_name=self._prop_name,
                options=options,
                candidate_context=candidate_context,
                allow_suggest_new=False,
            )
            log.bind(claude_selected_values=selected).info(
                "tags_multi_select_result"
            )
            return selected


class FormatTagsStep(PipelineStep):
    """Format as Notion multi_select."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def step_id(self) -> str:
        return "format_tags"

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
            if not current_value:
                return None
            str_val = ", ".join(current_value) if isinstance(current_value, list) else str(current_value)
            formatted = format_value_for_notion(str_val, self._prop_schema)
            if formatted is not None:
                context.set_property(self._prop_name, formatted)
            return formatted


class TagsPipeline(Pipeline):
    """Resolve tags multi_select from place context."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def pipeline_id(self) -> str:
        return f"tags_{self._prop_name}"

    def steps(self) -> list[PipelineStep]:
        return [
            InferTagsStep(self._prop_name, self._prop_schema),
            FormatTagsStep(self._prop_name, self._prop_schema),
        ]
