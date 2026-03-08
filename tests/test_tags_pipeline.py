"""Unit tests for Tags custom pipeline."""

from app.custom_pipelines.tags import TagsPipeline
from app.models.schema import PropertySchema, SelectOption
from app.pipeline_lib.context import ContextKeys as CtxKeys, PipelineRunContext
from app.pipeline_lib.orchestration import _run_pipeline


class _FakeClaude:
    def __init__(self, selected_values: list[str]):
        self.selected_values = selected_values
        self.calls = []

    def choose_multi_select_from_context(
        self, field_name, options, candidate_context, *, allow_suggest_new=False
    ):
        self.calls.append(
            {
                "field_name": field_name,
                "options": options,
                "candidate_context": candidate_context,
                "allow_suggest_new": allow_suggest_new,
            }
        )
        return self.selected_values


def _schema_with_options() -> PropertySchema:
    return PropertySchema(
        name="Tags",
        type="multi_select",
        options=[
            SelectOption(id="1", name="Landmark", color="blue"),
            SelectOption(id="2", name="History", color="gray"),
            SelectOption(id="3", name="Always Free", color="green"),
        ],
    )


def test_tags_pipeline_sets_property_when_claude_returns_values():
    """Pipeline writes multi_select property when Claude returns allowed options."""
    schema = _schema_with_options()
    pipeline = TagsPipeline("Tags", schema)
    fake_claude = _FakeClaude(["Landmark", "History"])
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Stone Arch Bridge",
                "formattedAddress": "Portland Ave",
                "primaryType": "bridge",
                "types": ["bridge", "landmark", "tourist_attraction"],
                "editorialSummary": "Historic bridge",
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Tags" in props
    assert props["Tags"]["multi_select"] == [
        {"name": "Landmark"},
        {"name": "History"},
    ]
    assert fake_claude.calls[0]["field_name"] == "Tags"
    assert fake_claude.calls[0]["options"] == ["Landmark", "History", "Always Free"]
    assert fake_claude.calls[0]["allow_suggest_new"] is True


def test_tags_pipeline_omits_property_when_no_values():
    """Pipeline leaves Tags unset when Claude returns empty list."""
    schema = _schema_with_options()
    pipeline = TagsPipeline("Tags", schema)
    fake_claude = _FakeClaude([])
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Generic Spot",
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
    assert "Tags" not in props


def test_tags_pipeline_omits_property_when_no_place():
    """Pipeline does not set Tags when google_place is missing."""
    schema = _schema_with_options()
    pipeline = TagsPipeline("Tags", schema)
    fake_claude = _FakeClaude(["Landmark"])
    ctx = PipelineRunContext(
        run_id="r1",
        initial={"_claude_service": fake_claude},
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Tags" not in props
    assert len(fake_claude.calls) == 0
