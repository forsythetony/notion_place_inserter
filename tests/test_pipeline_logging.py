"""Unit tests for pipeline orchestration logging."""

import pytest

from app.pipeline_lib.context import PipelineRunContext
from app.pipeline_lib.core import GlobalPipeline, Pipeline, PipelineStep, Stage
from app.pipeline_lib.orchestration import (
    run_global_pipeline,
    run_stage,
    _run_pipeline,
    _run_parallel_pipelines,
)
from loguru import logger


def _make_mock_step(step_id: str, docstring: str = ""):
    """Create a mock step that returns None."""
    class MockStep(PipelineStep):
        __doc__ = docstring

        @property
        def step_id(self) -> str:
            return step_id

        def execute(self, context, current_value):
            return None

    return MockStep()


def _make_mock_pipeline(pipeline_id: str, docstring: str = ""):
    """Create a mock pipeline with one no-op step."""
    class MockPipeline(Pipeline):
        __doc__ = docstring

        @property
        def pipeline_id(self) -> str:
            return pipeline_id

        def steps(self):
            return [_make_mock_step("mock_step", "A mock step")]

    return MockPipeline()


def _make_mock_stage(stage_id: str, pipelines_list: list, run_mode: str = "parallel", docstring: str = ""):
    """Create a mock stage."""
    class MockStage(Stage):
        __doc__ = docstring

        def __init__(self, pipelines: list, mode: str):
            self._pipelines = pipelines
            self._mode = mode

        @property
        def stage_id(self) -> str:
            return stage_id

        @property
        def run_mode(self) -> str:
            return self._mode

        def _pipelines_impl(self, context):
            return self._pipelines

    return MockStage(pipelines_list, run_mode)


def _make_mock_global_pipeline(stages_list: list, docstring: str = ""):
    """Create a mock global pipeline."""
    class MockGlobalPipeline(GlobalPipeline):
        __doc__ = docstring

        def __init__(self, stages: list):
            self._stages = stages

        @property
        def pipeline_id(self) -> str:
            return "test_global_pipeline"

        @property
        def schema_binding(self) -> str:
            return "TestDB"

        def stages(self):
            return self._stages

    return MockGlobalPipeline(stages_list)


@pytest.fixture
def captured_logs():
    """Capture loguru output for assertions."""
    output = []

    def sink(message):
        record = message.record
        output.append({
            "message": record["message"],
            "extra": dict(record["extra"]),
            "level": record["level"].name,
        })

    handler_id = logger.add(sink, level="DEBUG", format="{message}")
    yield output
    logger.remove(handler_id)


def test_sequential_pipeline_emits_start_success_with_metadata(captured_logs):
    """Sequential pipeline run emits pipeline_started and pipeline_completed with descriptive metadata."""
    context = PipelineRunContext(run_id="run-1", initial={})
    context.set("_global_pipeline_id", "gp-1")
    context.set("_current_stage_id", "stage-1")

    pipeline = _make_mock_pipeline("test_pipeline", "A test pipeline")
    _run_pipeline(pipeline, context, "run-1", "stage-1")

    started = next((e for e in captured_logs if "pipeline_started" in e["message"]), None)
    completed = next((e for e in captured_logs if "pipeline_completed" in e["message"]), None)

    assert started is not None
    assert completed is not None
    assert started["extra"]["pipeline"] == "test_pipeline"
    assert started["extra"]["event"] == "start"
    assert "pipeline_name" in started["extra"]
    assert "pipeline_description" in started["extra"]
    assert "step_count" in started["extra"]

    assert completed["extra"]["event"] == "success"
    assert "duration_ms" in completed["extra"]


def test_pipeline_failure_emits_failure_with_duration(captured_logs):
    """Pipeline failure emits pipeline_failed with event=failure and duration_ms."""
    class FailingStep(PipelineStep):
        @property
        def step_id(self) -> str:
            return "failing_step"

        def execute(self, context, current_value):
            raise ValueError("step failed")

    class FailingPipeline(Pipeline):
        @property
        def pipeline_id(self) -> str:
            return "failing_pipeline"

        def steps(self):
            return [FailingStep()]

    context = PipelineRunContext(run_id="run-1", initial={})
    context.set("_global_pipeline_id", "gp-1")
    context.set("_current_stage_id", "stage-1")

    with pytest.raises(ValueError, match="step failed"):
        _run_pipeline(FailingPipeline(), context, "run-1", "stage-1")

    failed = next((e for e in captured_logs if "pipeline_failed" in e["message"]), None)
    assert failed is not None
    assert failed["extra"]["event"] == "failure"
    assert "duration_ms" in failed["extra"]
    assert failed["level"] == "ERROR"


def test_stage_emits_descriptive_metadata(captured_logs):
    """Stage run emits stage_started and stage_completed with name, description, run_mode, pipeline_count."""
    context = PipelineRunContext(run_id="run-1", initial={})
    context.set("_global_pipeline_id", "gp-1")

    pipeline = _make_mock_pipeline("p1", "Pipeline one")
    stage = _make_mock_stage("test_stage", [pipeline], "sequential", "A test stage")

    run_stage(stage, context)

    started = next((e for e in captured_logs if "stage_started" in e["message"]), None)
    completed = next((e for e in captured_logs if "stage_completed" in e["message"]), None)

    assert started is not None
    assert completed is not None
    assert started["extra"]["stage_name"] == "test_stage"
    assert "stage_description" in started["extra"]
    assert started["extra"]["stage_run_mode"] == "sequential"
    assert started["extra"]["pipeline_count"] == 1
    assert "duration_ms" in completed["extra"]


def test_global_pipeline_emits_descriptive_metadata(captured_logs):
    """Global pipeline run emits global_pipeline_started/completed with name, description, stage_count."""
    context = PipelineRunContext(run_id="run-1", initial={})
    pipeline = _make_mock_pipeline("p1", "Pipeline one")
    stage = _make_mock_stage("s1", [pipeline], "sequential", "Stage one")
    global_pipeline = _make_mock_global_pipeline([stage], "Test global pipeline")

    run_global_pipeline(global_pipeline, context)

    started = next((e for e in captured_logs if "global_pipeline_started" in e["message"]), None)
    completed = next((e for e in captured_logs if "global_pipeline_completed" in e["message"]), None)

    assert started is not None
    assert completed is not None
    assert "global_pipeline_name" in started["extra"]
    assert "global_pipeline_description" in started["extra"]
    assert started["extra"]["stage_count"] == 1
    assert "duration_ms" in completed["extra"]


def test_parallel_stage_emits_fan_out_and_join_metadata(captured_logs):
    """Parallel stage emits stage_fan_out_started with pipeline_count."""
    context = PipelineRunContext(run_id="run-1", initial={})
    context.set("_global_pipeline_id", "gp-1")

    p1 = _make_mock_pipeline("p1", "Pipeline 1")
    p2 = _make_mock_pipeline("p2", "Pipeline 2")
    stage = _make_mock_stage("parallel_stage", [p1, p2], "parallel", "Parallel stage")

    run_stage(stage, context)

    fan_out = next((e for e in captured_logs if "stage_fan_out_started" in e["message"]), None)
    completed = next((e for e in captured_logs if "stage_completed" in e["message"]), None)

    assert fan_out is not None
    assert fan_out["extra"]["pipeline_count"] == 2
    assert completed is not None
    assert completed["extra"]["event"] == "join_complete"


def test_parallel_pipeline_failure_isolated_logs_warning(captured_logs):
    """When a pipeline fails in parallel mode, pipeline_failed_isolated is logged (warning)."""
    class FailingPipeline(Pipeline):
        @property
        def pipeline_id(self) -> str:
            return "failing_parallel_pipeline"

        def steps(self):
            class FailingStep(PipelineStep):
                @property
                def step_id(self) -> str:
                    return "fail"

                def execute(self, context, current_value):
                    raise RuntimeError("isolated failure")

            return [FailingStep()]

    context = PipelineRunContext(run_id="run-1", initial={})
    context.set("_global_pipeline_id", "gp-1")

    p_ok = _make_mock_pipeline("ok_pipeline", "OK")
    p_fail = FailingPipeline()
    stage = _make_mock_stage("parallel_stage", [p_ok, p_fail], "parallel", "Parallel")

    run_stage(stage, context)

    isolated = next((e for e in captured_logs if "pipeline_failed_isolated" in e["message"]), None)
    assert isolated is not None
    assert isolated["level"] == "WARNING"
    assert isolated["extra"]["pipeline"] == "failing_parallel_pipeline"
    assert "pipeline_name" in isolated["extra"]


def test_parallel_pipelines_context_isolation(captured_logs):
    """Parallel pipelines each emit logs with correct pipeline-scoped metadata (no cross-thread pollution)."""
    context = PipelineRunContext(run_id="run-1", initial={})
    context.set("_global_pipeline_id", "gp-1")

    p1 = _make_mock_pipeline("pipeline_a", "Pipeline A")
    p2 = _make_mock_pipeline("pipeline_b", "Pipeline B")
    stage = _make_mock_stage("parallel_stage", [p1, p2], "parallel", "Parallel")

    run_stage(stage, context)

    pipeline_started_logs = [e for e in captured_logs if "pipeline_started" in e["message"]]
    pipeline_completed_logs = [e for e in captured_logs if "pipeline_completed" in e["message"]]

    assert len(pipeline_started_logs) == 2
    assert len(pipeline_completed_logs) == 2

    pipeline_ids = {e["extra"]["pipeline"] for e in pipeline_started_logs}
    assert pipeline_ids == {"pipeline_a", "pipeline_b"}

    for log in pipeline_started_logs:
        assert log["extra"]["run_id"] == "run-1"
        assert log["extra"]["stage"] == "parallel_stage"
