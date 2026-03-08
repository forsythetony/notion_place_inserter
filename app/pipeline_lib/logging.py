"""Structured logging helpers for pipeline orchestration.

Uses contextvars for scoped context propagation. Lifecycle helpers emit
concise event messages; contextual metadata is bound and rendered by the
configured log format.
"""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from app.pipeline_lib.context import PipelineRunContext
    from app.pipeline_lib.core import GlobalPipeline, Pipeline, Stage

# Thread-safe scoped context. Each scope merges with parent; exit restores.
_log_context: ContextVar[dict[str, Any]] = ContextVar(
    "pipeline_log_context", default={}
)


def _get_context() -> dict[str, Any]:
    """Return current logging context (read-only copy)."""
    return dict(_log_context.get())


def _emit(message: str, level: str, **overrides: Any) -> None:
    """Emit log with merged context. Overrides take precedence."""
    ctx = _get_context()
    merged = {**ctx, **overrides}
    bound = logger.bind(**merged)
    getattr(bound, level.lower())(message)


@contextmanager
def log_context(**fields: Any):
    """Push fields to logging context for the scope. Restores on exit."""
    current = _log_context.get().copy()
    new_ctx = {**current, **{k: v for k, v in fields.items() if v is not None}}
    token = _log_context.set(new_ctx)
    try:
        yield
    finally:
        _log_context.reset(token)


@contextmanager
def log_global_pipeline(global_pipeline: "GlobalPipeline", context: "PipelineRunContext"):
    """Lifecycle scope for global pipeline. Emits start/completed/failed."""
    run_id = context.run_id
    gp_id = global_pipeline.pipeline_id
    context.set("_global_pipeline_id", gp_id)

    with log_context(
        run_id=run_id,
        global_pipeline=gp_id,
        global_pipeline_name=global_pipeline.name,
        global_pipeline_description=global_pipeline.description,
        stage_count=len(global_pipeline.stages()),
    ):
        _emit("global_pipeline_started", "INFO", event="start")
        start = time.monotonic()
        try:
            yield
            duration_ms = (time.monotonic() - start) * 1000
            _emit(
                "global_pipeline_completed",
                "INFO",
                event="success",
                duration_ms=round(duration_ms, 2),
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            _emit(
                "global_pipeline_failed",
                "ERROR",
                event="failure",
                duration_ms=round(duration_ms, 2),
                error=str(e),
            )
            raise


class _StageResult:
    """Mutable container for stage result (e.g. failed_count in parallel mode)."""

    failed_count: int = 0


@contextmanager
def log_stage(stage: "Stage", context: "PipelineRunContext"):
    """Lifecycle scope for a stage. Yields a result object; set result.failed_count
    for parallel stages. Emits start/completed/failed."""
    run_id = context.run_id
    stage_id = stage.stage_id
    pipelines_list = stage.pipelines(context)
    pipeline_count = len(pipelines_list)
    result = _StageResult()

    with log_context(
        run_id=run_id,
        global_pipeline=context.get("_global_pipeline_id", ""),
        stage=stage_id,
        stage_name=stage.name,
        stage_description=stage.description,
        stage_run_mode=stage.run_mode,
        pipeline_count=pipeline_count,
    ):
        _emit("stage_started", "INFO", event="start")
        start = time.monotonic()
        try:
            yield result
            duration_ms = (time.monotonic() - start) * 1000
            extra: dict[str, Any] = {}
            if stage.run_mode == "parallel" and result.failed_count > 0:
                extra["failed_pipeline_count"] = result.failed_count
            _emit(
                "stage_completed",
                "INFO",
                event="join_complete" if stage.run_mode == "parallel" else "success",
                duration_ms=round(duration_ms, 2),
                **extra,
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            _emit(
                "stage_failed",
                "ERROR",
                event="failure",
                duration_ms=round(duration_ms, 2),
                error=str(e),
            )
            raise


@contextmanager
def log_pipeline(
    pipeline: "Pipeline",
    context: "PipelineRunContext",
    run_id: str,
    stage_id: str,
):
    """Lifecycle scope for a pipeline. Emits start/completed/failed."""
    context.set("_current_stage_id", stage_id)
    context.set("_current_pipeline_id", pipeline.pipeline_id)

    with log_context(
        run_id=run_id,
        global_pipeline=context.get("_global_pipeline_id", ""),
        stage=stage_id,
        pipeline=pipeline.pipeline_id,
        pipeline_name=pipeline.name,
        pipeline_description=pipeline.description,
        step_count=len(pipeline.steps()),
    ):
        _emit("pipeline_started", "INFO", event="start")
        start = time.monotonic()
        try:
            yield
            duration_ms = (time.monotonic() - start) * 1000
            _emit(
                "pipeline_completed",
                "INFO",
                event="success",
                duration_ms=round(duration_ms, 2),
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            _emit(
                "pipeline_failed",
                "ERROR",
                event="failure",
                duration_ms=round(duration_ms, 2),
                error=str(e),
            )
            raise


@contextmanager
def log_pipeline_fan_out(
    run_id: str,
    stage_id: str,
    pipeline_count: int,
    global_pipeline_id: str = "",
):
    """Emit stage_fan_out_started. Used when entering parallel stage fan-out."""
    with log_context(
        run_id=run_id,
        global_pipeline=global_pipeline_id,
        stage=stage_id,
        pipeline_count=pipeline_count,
    ):
        _emit("stage_fan_out_started", "INFO", event="join_wait")
        yield


def log_pipeline_failed_isolated(
    run_id: str,
    stage_id: str,
    global_pipeline_id: str,
    pipeline: "Pipeline",
    error: Exception,
) -> None:
    """Emit pipeline_failed_isolated (parallel stage, non-propagating)."""
    with log_context(
        run_id=run_id,
        global_pipeline=global_pipeline_id,
        stage=stage_id,
        pipeline=pipeline.pipeline_id,
        pipeline_name=pipeline.name,
        pipeline_description=pipeline.description,
        event="failure",
    ):
        logger.bind(**_get_context()).warning(
            "pipeline_failed_isolated",
            error=str(error),
        )


class _RequestResult:
    """Mutable container for request result (e.g. property_count)."""

    property_count: int = 0


@contextmanager
def log_pipeline_request(
    run_id: str,
    keywords_preview: str,
    dry_run: bool = False,
):
    """Lifecycle scope for a pipeline request (e.g. from PlacesService).
    Yields a result object; set result.property_count before exit for completed log.
    Emits pipeline_request_started/completed/failed."""
    result = _RequestResult()
    with log_context(
        run_id=run_id,
        keywords_preview=keywords_preview,
        dry_run=dry_run,
    ):
        _emit("pipeline_request_started", "INFO")
        start = time.monotonic()
        try:
            yield result
            duration_ms = (time.monotonic() - start) * 1000
            _emit(
                "pipeline_request_completed",
                "INFO",
                duration_ms=round(duration_ms, 2),
                property_count=result.property_count,
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            _emit(
                "pipeline_request_failed",
                "ERROR",
                duration_ms=round(duration_ms, 2),
                error=str(e),
            )
            raise


def bind_orchestration(
    run_id: str,
    global_pipeline: str,
    stage: str | None = None,
    pipeline: str | None = None,
    step: str | None = None,
    event: str | None = None,
    duration_ms: float | None = None,
    context_key: str | None = None,
    *,
    step_name: str | None = None,
    step_description: str | None = None,
    step_index: int | None = None,
    step_count: int | None = None,
    property_name: str | None = None,
    property_type: str | None = None,
    **extra: Any,
) -> Any:
    """Return a loguru-bound logger with orchestration identity fields.
    Used by log_step and for one-off emits."""
    ctx = _get_context()
    kwargs: dict[str, Any] = {
        **ctx,
        "run_id": run_id,
        "global_pipeline": global_pipeline,
    }
    if stage is not None:
        kwargs["stage"] = stage
    if pipeline is not None:
        kwargs["pipeline"] = pipeline
    if step is not None:
        kwargs["step"] = step
    if event is not None:
        kwargs["event"] = event
    if duration_ms is not None:
        kwargs["duration_ms"] = duration_ms
    if context_key is not None:
        kwargs["context_key"] = context_key
    if step_name is not None:
        kwargs["step_name"] = step_name
    if step_description is not None:
        kwargs["step_description"] = step_description
    if step_index is not None:
        kwargs["step_index"] = step_index
    if step_count is not None:
        kwargs["step_count"] = step_count
    if property_name is not None:
        kwargs["property_name"] = property_name
    if property_type is not None:
        kwargs["property_type"] = property_type
    kwargs.update(extra)
    return logger.bind(**kwargs)


@contextmanager
def log_step(
    run_id: str,
    global_pipeline: str,
    stage: str,
    pipeline: str,
    step: str,
    *,
    step_name: str | None = None,
    step_description: str | None = None,
    step_index: int | None = None,
    step_count: int | None = None,
    property_name: str | None = None,
    property_type: str | None = None,
    **extra: Any,
):
    """Context manager that logs step start/success/failure with duration.
    Merges step fields into ambient context for the scope."""
    step_kwargs: dict[str, Any] = {
        "step_name": step_name,
        "step_description": step_description,
        "step_index": step_index,
        "step_count": step_count,
        "property_name": property_name,
        "property_type": property_type,
    }
    step_kwargs.update(extra)
    step_kwargs = {k: v for k, v in step_kwargs.items() if v is not None}

    with log_context(
        run_id=run_id,
        global_pipeline=global_pipeline,
        stage=stage,
        pipeline=pipeline,
        step=step,
        **step_kwargs,
    ):
        _emit("step_start", "INFO")
        start = time.monotonic()
        try:
            yield
            duration_ms = (time.monotonic() - start) * 1000
            _emit("step_complete", "INFO", event="success", duration_ms=round(duration_ms, 2))
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            _emit(
                "step_failed",
                "ERROR",
                event="failure",
                duration_ms=round(duration_ms, 2),
                error=str(e),
            )
            raise
