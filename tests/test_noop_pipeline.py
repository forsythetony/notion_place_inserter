"""Unit tests for NoOp pipeline: intentionally skipped properties."""

from app.custom_pipelines.no_op import NoOpPipeline
from app.models.schema import PropertySchema
from app.pipeline_lib.context import ContextKeys as CtxKeys, PipelineRunContext
from app.pipeline_lib.orchestration import _run_pipeline


def test_noop_pipeline_omits_property_from_payload():
    """NoOpPipeline does not add the property to get_properties (omitted from Notion payload)."""
    schema = PropertySchema(name="Yelp", type="url", options=None)
    pipeline = NoOpPipeline("Yelp", schema)
    ctx = PipelineRunContext(run_id="r1", initial={})
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Yelp" not in props


def test_noop_pipeline_records_property_skip():
    """NoOpPipeline records the property in get_property_skips for dry-run display."""
    schema = PropertySchema(name="Yelp", type="url", options=None)
    pipeline = NoOpPipeline("Yelp", schema)
    ctx = PipelineRunContext(run_id="r1", initial={})
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    skips = ctx.get_property_skips()
    assert "Yelp" in skips
    assert skips["Yelp"] == "noop_Yelp"


def test_noop_pipeline_does_not_record_property_source():
    """NoOpPipeline does not add the property to get_property_sources."""
    schema = PropertySchema(name="Yelp", type="url", options=None)
    pipeline = NoOpPipeline("Yelp", schema)
    ctx = PipelineRunContext(run_id="r1", initial={})
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    sources = ctx.get_property_sources()
    assert "Yelp" not in sources
