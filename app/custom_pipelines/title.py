"""Custom pipeline for Title/Name property: ExtractDisplayName -> FormatAsNotionTitle."""

from app.models.schema import PropertySchema
from app.pipeline_lib.core import Pipeline, PipelineStep
from app.pipeline_lib.steps.google_places import ExtractDisplayName
from app.pipeline_lib.steps.notion_format import FormatAsNotionTitle


class TitlePipeline(Pipeline):
    """Resolve title from Google Places displayName."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def pipeline_id(self) -> str:
        return f"title_{self._prop_name}"

    def steps(self) -> list[PipelineStep]:
        return [
            ExtractDisplayName(),
            FormatAsNotionTitle(self._prop_name),
        ]
