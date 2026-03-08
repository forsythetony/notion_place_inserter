"""Unit tests for Main Type/Primary Type custom pipeline."""

from loguru import logger

from app.custom_pipelines.primary_type import PrimaryTypePipeline
from app.models.schema import PropertySchema, SelectOption
from app.pipeline_lib.context import ContextKeys as CtxKeys, PipelineRunContext
from app.pipeline_lib.orchestration import _run_pipeline


class _FakeClaude:
    def __init__(self, selected_value):
        self.selected_value = selected_value
        self.calls = []

    def choose_option_from_context(self, field_name, options, candidate_context):
        self.calls.append(
            {
                "field_name": field_name,
                "options": options,
                "candidate_context": candidate_context,
            }
        )
        return self.selected_value


def _schema_with_options() -> PropertySchema:
    return PropertySchema(
        name="Main Type",
        type="select",
        options=[
            SelectOption(id="1", name="Museum", color="blue"),
            SelectOption(id="2", name="Park", color="green"),
        ],
    )


def _capture_logs():
    captured = []

    def sink(message):
        record = message.record
        captured.append(
            {
                "message": record["message"],
                "extra": dict(record["extra"]),
                "level": record["level"].name,
            }
        )

    handler_id = logger.add(sink, level="INFO", format="{message}")
    return captured, handler_id


def test_primary_type_pipeline_sets_property_when_claude_returns_allowed_option():
    """Pipeline writes select property when Claude returns an allowed option."""
    schema = _schema_with_options()
    pipeline = PrimaryTypePipeline("Main Type", schema)
    fake_claude = _FakeClaude("Park")
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Loring Park",
                "formattedAddress": "1382 Willow St",
                "primaryType": "park",
                "types": ["park", "tourist_attraction"],
                "rating": 4.7,
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert props["Main Type"] == {"select": {"name": "Park"}}
    assert fake_claude.calls[0]["field_name"] == "Main Type"
    assert fake_claude.calls[0]["options"] == ["Museum", "Park"]
    assert fake_claude.calls[0]["candidate_context"]["primaryType"] == "park"


def test_primary_type_pipeline_omits_property_when_no_match():
    """Pipeline leaves Main Type unset when Claude returns no match."""
    schema = _schema_with_options()
    pipeline = PrimaryTypePipeline("Main Type", schema)
    fake_claude = _FakeClaude(None)
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Unknown Spot",
                "formattedAddress": "123 Test Ave",
                "primaryType": "point_of_interest",
                "types": ["point_of_interest"],
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Main Type" not in props


def test_primary_type_pipeline_logs_request_context_and_result():
    """Pipeline logs requested property/options/context and Claude-selected value."""
    schema = _schema_with_options()
    pipeline = PrimaryTypePipeline("Main Type", schema)
    fake_claude = _FakeClaude("Museum")
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "City Museum",
                "formattedAddress": "100 Main St",
                "primaryType": "museum",
                "types": ["museum", "point_of_interest"],
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    logs, handler_id = _capture_logs()
    try:
        _run_pipeline(pipeline, ctx, "r1", "s1")
    finally:
        logger.remove(handler_id)

    request_log = next(
        e for e in logs if e["message"] == "main_type_option_selection_request"
    )
    assert request_log["extra"]["property_name"] == "Main Type"
    assert request_log["extra"]["options"] == ["Museum", "Park"]
    assert request_log["extra"]["candidate_context"]["primaryType"] == "museum"

    result_log = next(
        e for e in logs if e["message"] == "main_type_option_selection_result"
    )
    assert result_log["extra"]["claude_selected_value"] == "Museum"
