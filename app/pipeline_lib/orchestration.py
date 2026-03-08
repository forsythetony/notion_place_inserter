"""Stage runner with sequential/parallel execution and fan-out/join logic."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from app.pipeline_lib.context import PipelineRunContext, set_active_pipeline_id
from app.pipeline_lib.core import Pipeline, Stage
from app.pipeline_lib.logging import (
    log_global_pipeline,
    log_pipeline,
    log_pipeline_failed_isolated,
    log_pipeline_fan_out,
    log_stage,
)

if TYPE_CHECKING:
    from app.pipeline_lib.core import GlobalPipeline


def run_global_pipeline(
    global_pipeline: "GlobalPipeline",
    context: PipelineRunContext,
) -> None:
    """Run all stages of a global pipeline in order."""
    with log_global_pipeline(global_pipeline, context):
        for stage in global_pipeline.stages():
            stage.run(context)


def run_stage(stage: Stage, context: PipelineRunContext) -> None:
    """Run a stage's pipelines (sequential or parallel)."""
    with log_stage(stage, context) as result:
        if stage.run_mode == "parallel":
            result.failed_count = _run_parallel_pipelines(
                stage.pipelines(context), context, context.run_id, stage.stage_id
            )
        else:
            for pipeline in stage.pipelines(context):
                _run_pipeline(pipeline, context, context.run_id, stage.stage_id)


def _run_pipeline(
    pipeline: Pipeline,
    context: PipelineRunContext,
    run_id: str,
    stage_id: str,
) -> None:
    """Run a single pipeline. Failures are logged but may propagate."""
    set_active_pipeline_id(pipeline.pipeline_id)
    try:
        with log_pipeline(pipeline, context, run_id, stage_id):
            pipeline.run(context)
    finally:
        set_active_pipeline_id(None)


def _run_parallel_pipelines(
    pipelines: list[Pipeline],
    context: PipelineRunContext,
    run_id: str,
    stage_id: str,
) -> int:
    """Fan out pipelines, run concurrently, join. Per-pipeline failures are isolated.
    Returns the number of pipelines that failed."""
    gp_id = context.get("_global_pipeline_id", "")
    with log_pipeline_fan_out(run_id, stage_id, len(pipelines), gp_id):
        errors: list[tuple[str, Exception]] = []
        with ThreadPoolExecutor(max_workers=len(pipelines)) as executor:
            futures = {
                executor.submit(_run_pipeline, p, context, run_id, stage_id): p
                for p in pipelines
            }
            for future in as_completed(futures):
                pipeline = futures[future]
                try:
                    future.result()
                except Exception as e:
                    errors.append((pipeline.pipeline_id, e))
                    log_pipeline_failed_isolated(
                        run_id, stage_id, gp_id, pipeline, e
                    )
        return len(errors)
