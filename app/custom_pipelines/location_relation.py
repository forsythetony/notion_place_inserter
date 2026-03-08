"""Custom pipeline for Location relation: match or create Locations DB page."""

from app.models.schema import PropertySchema
from app.pipeline_lib.core import Pipeline, PipelineStep
from app.pipeline_lib.steps.location_relation import (
    BuildLocationCandidateStep,
    FormatLocationRelationForNotionStep,
    ResolveLocationRelationStep,
)


class LocationRelationPipeline(Pipeline):
    """Resolve Places-to-Locations relation: link to existing or create new location page."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def pipeline_id(self) -> str:
        return f"location_relation_{self._prop_name}"

    def steps(self) -> list[PipelineStep]:
        return [
            BuildLocationCandidateStep(self._prop_name),
            ResolveLocationRelationStep(self._prop_name),
            FormatLocationRelationForNotionStep(self._prop_name),
        ]
