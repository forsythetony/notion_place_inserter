"""Schema-related stage pipelines."""

from app.pipeline_lib.context import ContextKeys, PipelineRunContext
from app.pipeline_lib.core import Pipeline, PipelineStep
from app.pipeline_lib.logging import log_step


class FetchSchemaStep(PipelineStep):
    """Fetch the latest schema for the bound database and store in context."""

    def __init__(self, db_name: str):
        self._db_name = db_name

    @property
    def step_id(self) -> str:
        return "fetch_schema"

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
        ):
            notion = context.get("_notion_service")
            if not notion:
                return None
            schema = notion.get_database_schema(self._db_name)
            context.set(ContextKeys.SCHEMA, schema)
            return schema


class LoadLatestSchemaPipeline(Pipeline):
    """Pipeline that fetches the newest schema for the bound database."""

    def __init__(self, db_name: str):
        self._db_name = db_name

    @property
    def pipeline_id(self) -> str:
        return "load_latest_schema"

    def steps(self) -> list[PipelineStep]:
        return [FetchSchemaStep(self._db_name)]
