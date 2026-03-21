"""Tests for standardized pipeline step logging."""

from datetime import datetime, timezone

from app.services.job_execution.step_pipeline_log import (
    StepPipelineLog,
    build_step_input_summary,
    build_step_output_summary,
    emit_step_final,
    emit_step_input,
    json_safe_for_db,
    sanitize_for_step_log,
)


def test_sanitize_for_step_log_truncates_long_strings():
    s = "x" * 200
    out = sanitize_for_step_log({"k": s}, max_str=50)
    assert isinstance(out, dict)
    assert len(out["k"]) <= 50
    assert out["k"].endswith("...")


def test_emit_step_input_final_and_processing_markers():
    """Emitted logs contain pipeline_step INPUT, PROCESSING, FINAL markers."""
    from loguru import logger

    lines: list[str] = []

    def sink(message):
        lines.append(message)

    hid = logger.add(sink, level="INFO", format="{message}")
    try:
        log = StepPipelineLog(
            run_id="r1",
            job_id="j1",
            stage_id="st1",
            pipeline_id="p1",
            step_id="s1",
            step_template_id="tmpl",
        )
        emit_step_input(
            log,
            resolved_inputs={"query": "hi"},
            input_bindings={"query": {"signal_ref": "trigger.payload.keywords"}},
            config={"a": 1},
        )
        log.processing("middle step")
        emit_step_final(
            log,
            outputs={"out": "done"},
            status="succeeded",
            runtime_ms=12.5,
        )
    finally:
        logger.remove(hid)

    combined = "\n".join(lines)
    assert "pipeline_step | INPUT" in combined
    assert "INPUT LOG:" in combined
    assert "pipeline_step | PROCESSING" in combined
    assert "middle step" in combined
    assert "pipeline_step | FINAL" in combined
    assert "FINAL LOG:" in combined
    assert "Status: succeeded" in combined
    assert "Runtime_ms: 12.50" in combined


def test_json_safe_for_db_handles_datetime_and_tuple():
    """PostgREST jsonb requires JSON-serializable structures (no raw datetime/tuple)."""
    dt = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    out = json_safe_for_db({"t": (1, 2), "d": dt})
    assert out["t"] == [1, 2]
    assert "2026-01-02" in out["d"]


def test_build_step_input_and_output_summary_v1():
    log = StepPipelineLog(
        run_id="r1",
        job_id="j1",
        stage_id="st1",
        pipeline_id="p1",
        step_id="s1",
        step_template_id="tmpl",
    )
    inp = build_step_input_summary(
        log,
        resolved_inputs={"q": "hi", "ts": datetime(2026, 3, 20, tzinfo=timezone.utc)},
        input_bindings={"q": {"signal_ref": "trigger.x"}},
        config={"a": 1},
    )
    assert inp["schema_version"] == 1
    assert "2026-03-20" in str(inp["resolved_inputs"]["ts"])
    assert inp["meta"]["step_id"] == "s1"
    assert inp["resolved_inputs"]["q"] == "hi"
    assert inp["input_bindings"]["q"]["signal_ref"] == "trigger.x"
    out = build_step_output_summary(
        outputs={"o": "x"},
        status="succeeded",
        runtime_ms=1.234567,
    )
    assert out["schema_version"] == 1
    assert out["status"] == "succeeded"
    assert out["error"] is None
    assert out["runtime_ms"] == 1.2346


def test_processing_lines_accumulate():
    log = StepPipelineLog(
        run_id="r1",
        job_id="j1",
        stage_id="st1",
        pipeline_id="p1",
        step_id="s1",
        step_template_id="tmpl",
    )
    log.processing("a")
    log.processing("b")
    assert log.processing_lines == ["a", "b"]


def test_emit_step_final_failed_includes_error():
    from loguru import logger

    lines: list[str] = []

    def sink(message):
        lines.append(message)

    hid = logger.add(sink, level="INFO", format="{message}")
    try:
        log = StepPipelineLog(
            run_id="r1",
            job_id="j1",
            stage_id="st1",
            pipeline_id="p1",
            step_id="s1",
            step_template_id="tmpl",
        )
        emit_step_final(
            log,
            outputs={},
            status="failed",
            runtime_ms=3.0,
            error="boom",
        )
    finally:
        logger.remove(hid)

    combined = "\n".join(lines)
    assert "Status: failed" in combined
    assert "Error: boom" in combined
