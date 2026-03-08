"""Unit tests for ConstantValue pipeline: properties that always resolve to a fixed value."""

from app.custom_pipelines import CUSTOM_PIPELINE_REGISTRY
from app.custom_pipelines.constant_value import (
    ConstantValueStep,
    ConstantValuePipeline,
    SourcePipeline,
)
from app.models.schema import PropertySchema, SelectOption
from app.pipeline_lib.context import PipelineRunContext
from app.pipeline_lib.orchestration import _run_pipeline


def _source_schema() -> PropertySchema:
    return PropertySchema(
        name="Source",
        type="select",
        options=[
            SelectOption(id="opt1", name="Notion Place Inserter", color="blue"),
            SelectOption(id="opt2", name="Manual", color="gray"),
        ],
    )


def test_source_pipeline_writes_property_with_correct_select_payload():
    """SourcePipeline writes the property with correct Notion select payload."""
    schema = _source_schema()
    pipeline = SourcePipeline("Source", schema)
    ctx = PipelineRunContext(run_id="r1", initial={})
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Source" in props
    assert props["Source"] == {"select": {"name": "Notion Place Inserter"}}


def test_source_pipeline_records_property_source():
    """SourcePipeline records the property in get_property_sources for provenance."""
    schema = _source_schema()
    pipeline = SourcePipeline("Source", schema)
    ctx = PipelineRunContext(run_id="r1", initial={})
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    sources = ctx.get_property_sources()
    assert "Source" in sources
    assert sources["Source"] == "constant_value_Source"


def test_constant_value_step_ignores_input():
    """ConstantValueStep always resolves to constant regardless of current_value."""
    schema = _source_schema()
    step = ConstantValueStep("Source", schema, "Notion Place Inserter")

    for current_value in (None, "Manual", 42, {"foo": "bar"}):
        ctx = PipelineRunContext(run_id="r1", initial={})
        ctx.set("_global_pipeline_id", "gp")
        ctx.set("_current_stage_id", "s1")
        ctx.set("_current_pipeline_id", "p1")
        step.execute(ctx, current_value)
        props = ctx.get_properties()
        assert props["Source"] == {"select": {"name": "Notion Place Inserter"}}


def test_constant_value_pipeline_generic():
    """ConstantValuePipeline accepts generic constant value."""
    schema = PropertySchema(
        name="Status",
        type="select",
        options=[
            SelectOption(id="a", name="Active", color="green"),
            SelectOption(id="b", name="Inactive", color="gray"),
        ],
    )
    pipeline = ConstantValuePipeline("Status", schema, "Active")
    ctx = PipelineRunContext(run_id="r1", initial={})
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Status" in props
    assert props["Status"] == {"select": {"name": "Active"}}


def test_source_pipeline_registered():
    """CUSTOM_PIPELINE_REGISTRY maps Source to SourcePipeline."""
    assert CUSTOM_PIPELINE_REGISTRY.get("Source") is SourcePipeline
