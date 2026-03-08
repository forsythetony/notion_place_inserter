"""Unit tests for Description custom pipeline."""

from app.custom_pipelines.description import (
    DescriptionPipeline,
    _build_fact_pack,
    _deterministic_fallback,
)
from app.models.schema import PropertySchema
from app.pipeline_lib.context import ContextKeys as CtxKeys, PipelineRunContext
from app.pipeline_lib.orchestration import _run_pipeline


class _FakeClaude:
    def __init__(self, polished: str | None):
        self.polished = polished
        self.calls = []

    def polish_place_description(self, fact_pack: dict):
        self.calls.append({"fact_pack": fact_pack})
        return self.polished


def _notes_schema() -> PropertySchema:
    return PropertySchema(name="Notes", type="rich_text", options=None)


def test_description_pipeline_uses_claude_when_available():
    """Pipeline writes Notes when Claude returns polished text."""
    schema = _notes_schema()
    pipeline = DescriptionPipeline("Notes", schema)
    fake_claude = _FakeClaude("The Stone Arch Bridge is a historic landmark in Minneapolis.")
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Stone Arch Bridge",
                "formattedAddress": "Portland Ave, Minneapolis",
                "primaryType": "bridge",
                "types": ["bridge", "landmark"],
                "rating": 4.8,
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Notes" in props
    assert props["Notes"]["rich_text"][0]["text"]["content"] == (
        "The Stone Arch Bridge is a historic landmark in Minneapolis."
    )
    assert len(fake_claude.calls) == 1
    assert fake_claude.calls[0]["fact_pack"]["name"] == "Stone Arch Bridge"
    assert fake_claude.calls[0]["fact_pack"]["address"] == "Portland Ave, Minneapolis"


def test_description_pipeline_falls_back_when_claude_unavailable():
    """Pipeline uses deterministic fallback when Claude service is missing."""
    schema = _notes_schema()
    pipeline = DescriptionPipeline("Notes", schema)
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Stone Arch Bridge",
                "formattedAddress": "Portland Ave, Minneapolis",
                "rating": 4.8,
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Notes" in props
    content = props["Notes"]["rich_text"][0]["text"]["content"]
    assert "Stone Arch Bridge" in content
    assert "Portland Ave" in content
    assert "4.8" in content


def test_description_pipeline_falls_back_when_claude_raises():
    """Pipeline uses deterministic fallback when Claude raises."""
    schema = _notes_schema()
    pipeline = DescriptionPipeline("Notes", schema)

    class _FailingClaude:
        def polish_place_description(self, fact_pack):
            raise RuntimeError("API error")

    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": _FailingClaude(),
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Test Place",
                "formattedAddress": "123 Main St",
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Notes" in props
    content = props["Notes"]["rich_text"][0]["text"]["content"]
    assert "Test Place" in content
    assert "123 Main St" in content


def test_description_pipeline_uses_editorial_summary_in_fallback():
    """Deterministic fallback prefers editorialSummary when available."""
    schema = _notes_schema()
    pipeline = DescriptionPipeline("Notes", schema)
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Stone Arch Bridge",
                "formattedAddress": "Portland Ave",
                "editorialSummary": "Historic bridge spanning the Mississippi.",
                "rating": 4.8,
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Notes" in props
    content = props["Notes"]["rich_text"][0]["text"]["content"]
    assert "Historic bridge spanning the Mississippi" in content
    assert "4.8" in content


def test_description_pipeline_omits_property_when_no_place():
    """Pipeline does not set Notes when google_place is missing."""
    schema = _notes_schema()
    pipeline = DescriptionPipeline("Notes", schema)
    fake_claude = _FakeClaude("Polished text")
    ctx = PipelineRunContext(
        run_id="r1",
        initial={"_claude_service": fake_claude},
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Notes" not in props
    assert len(fake_claude.calls) == 0


def test_build_fact_pack_extracts_all_fields():
    """Fact pack includes name, address, type, summaries, rating."""
    place = {
        "displayName": "Stone Arch Bridge",
        "formattedAddress": "Portland Ave",
        "primaryType": "bridge",
        "types": ["bridge", "landmark"],
        "editorialSummary": "Historic bridge",
        "generativeSummary": "AI summary",
        "rating": 4.8,
    }
    pack = _build_fact_pack(place)
    assert pack["name"] == "Stone Arch Bridge"
    assert pack["address"] == "Portland Ave"
    assert pack["primaryType"] == "bridge"
    assert pack["editorialSummary"] == "Historic bridge"
    assert pack["generativeSummary"] == "AI summary"
    assert pack["rating"] == 4.8


def test_deterministic_fallback_uses_editorial_over_generative():
    """Fallback prefers editorialSummary over generativeSummary."""
    pack = {
        "name": "Place",
        "address": "123 St",
        "editorialSummary": "Editorial text",
        "generativeSummary": "Generative text",
    }
    result = _deterministic_fallback(pack)
    assert "Editorial text" in result
    assert "Generative text" not in result


def test_deterministic_fallback_uses_generative_when_no_editorial():
    """Fallback uses generativeSummary when editorialSummary is missing."""
    pack = {
        "name": "Place",
        "address": "123 St",
        "generativeSummary": "Generative text",
    }
    result = _deterministic_fallback(pack)
    assert "Generative text" in result


def test_deterministic_fallback_builds_from_name_address():
    """Fallback builds name at address when no summaries."""
    pack = {
        "name": "Test Place",
        "address": "456 Main St",
        "rating": 4.5,
    }
    result = _deterministic_fallback(pack)
    assert "Test Place" in result
    assert "456 Main St" in result
    assert "4.5" in result
