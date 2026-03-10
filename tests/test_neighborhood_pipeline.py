"""Unit tests for Neighborhood custom pipeline."""

from loguru import logger

from app.custom_pipelines.neighborhood import NeighborhoodPipeline
from app.models.schema import PropertySchema, SelectOption
from app.pipeline_lib.context import ContextKeys as CtxKeys, PipelineRunContext
from app.pipeline_lib.orchestration import _run_pipeline


class _FakeClaude:
    def __init__(self, value: str | None, is_new: bool = False):
        self.value = value
        self.is_new = is_new
        self.calls = []

    def choose_option_with_suggest_from_context(
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
        from app.services.claude_service import OptionSelectionResult

        return OptionSelectionResult(self.value, self.is_new)


def _schema_with_options() -> PropertySchema:
    return PropertySchema(
        name="Neighborhood",
        type="select",
        options=[
            SelectOption(id="1", name="South Minneapolis", color="blue"),
            SelectOption(id="2", name="North Loop", color="green"),
        ],
    )


def test_neighborhood_pipeline_sets_property_when_matching_existing_option():
    """Pipeline writes select property when Claude returns an allowed option."""
    schema = _schema_with_options()
    pipeline = NeighborhoodPipeline("Neighborhood", schema)
    fake_claude = _FakeClaude("South Minneapolis", is_new=False)
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Loring Park",
                "formattedAddress": "1382 Willow St, Minneapolis, MN",
                "neighborhood": "Loring Park",
                "primaryType": "park",
                "types": ["park", "tourist_attraction"],
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert props["Neighborhood"] == {"select": {"name": "South Minneapolis"}}
    assert fake_claude.calls[0]["field_name"] == "Neighborhood"
    assert fake_claude.calls[0]["options"] == ["South Minneapolis", "North Loop"]
    assert fake_claude.calls[0]["candidate_context"]["neighborhood"] == "Loring Park"
    assert fake_claude.calls[0]["allow_suggest_new"] is True


def test_neighborhood_pipeline_omits_property_when_no_value():
    """Pipeline leaves Neighborhood unset when Claude returns no value (e.g. national park)."""
    schema = _schema_with_options()
    pipeline = NeighborhoodPipeline("Neighborhood", schema)
    fake_claude = _FakeClaude(None)
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Yellowstone National Park",
                "formattedAddress": "Yellowstone, WY",
                "neighborhood": None,
                "primaryType": "park",
                "types": ["park", "natural_feature"],
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Neighborhood" not in props
    omissions = ctx.get_property_omissions()
    assert omissions["Neighborhood"]["pipeline_id"] == "neighborhood_Neighborhood"
    assert omissions["Neighborhood"]["reason"] == "no_value"


def test_neighborhood_pipeline_creates_new_and_logs_when_suggested():
    """Pipeline sets new neighborhood value and logs creation message."""
    schema = _schema_with_options()
    pipeline = NeighborhoodPipeline("Neighborhood", schema)
    fake_claude = _FakeClaude("Uptown", is_new=True)
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Muddy Waters",
                "formattedAddress": "1633 Lyndale Ave S, Minneapolis, MN",
                "neighborhood": "Uptown",
                "primaryType": "restaurant",
                "types": ["restaurant", "bar"],
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

    props = ctx.get_properties()
    assert props["Neighborhood"] == {"select": {"name": "Uptown"}}

    creation_log = next(
        (e for e in logs if "creating new neighborhood" in str(e.get("message", ""))),
        None,
    )
    assert creation_log is not None
    assert "Uptown" in str(creation_log.get("message", ""))


def test_neighborhood_pipeline_omits_property_when_no_place():
    """Pipeline does not set Neighborhood when google_place is missing."""
    schema = _schema_with_options()
    pipeline = NeighborhoodPipeline("Neighborhood", schema)
    fake_claude = _FakeClaude("South Minneapolis")
    ctx = PipelineRunContext(
        run_id="r1",
        initial={"_claude_service": fake_claude},
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Neighborhood" not in props
    assert len(fake_claude.calls) == 0


def test_neighborhood_pipeline_omits_property_when_no_claude():
    """Pipeline does not set Neighborhood when claude_service is missing."""
    schema = _schema_with_options()
    pipeline = NeighborhoodPipeline("Neighborhood", schema)
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Test Place",
                "formattedAddress": "123 Main St",
                "neighborhood": "Downtown",
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Neighborhood" not in props


def test_neighborhood_pipeline_creates_new_from_sublocality_level_1_without_claude():
    """Pipeline creates new neighborhood from sublocality_level_1 via deterministic path, no Claude call."""
    schema = _schema_with_options()
    pipeline = NeighborhoodPipeline("Neighborhood", schema)
    fake_claude = _FakeClaude("Uptown", is_new=True)  # would return this if called
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Blanco Colima",
                "formattedAddress": "Av. Álvaro Obregón, Roma Norte, CDMX",
                "neighborhood": "Roma Norte",
                "neighborhood_signal_type": "sublocality_level_1",
                "addressComponents": [
                    {
                        "longText": "Roma Norte",
                        "shortText": "Roma Nte.",
                        "types": ["sublocality_level_1", "sublocality", "political"],
                    },
                    {"longText": "Ciudad de México", "shortText": "CDMX", "types": ["locality"]},
                ],
                "primaryType": "restaurant",
                "types": ["restaurant"],
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert props["Neighborhood"] == {"select": {"name": "Roma Norte"}}
    assert len(fake_claude.calls) == 0


def test_neighborhood_pipeline_creates_new_from_neighborhood_signal_without_claude():
    """Pipeline creates new neighborhood from neighborhood signal type via deterministic path."""
    schema = PropertySchema(
        name="Neighborhood",
        type="select",
        options=[SelectOption(id="1", name="Downtown", color="blue")],
    )
    pipeline = NeighborhoodPipeline("Neighborhood", schema)
    fake_claude = _FakeClaude(None)
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Local Cafe",
                "formattedAddress": "123 Main St, Barrio Nuevo",
                "neighborhood": "Barrio Nuevo",
                "neighborhood_signal_type": "neighborhood",
                "addressComponents": [
                    {"longText": "Barrio Nuevo", "shortText": "Barrio N.", "types": ["neighborhood"]},
                ],
                "primaryType": "cafe",
                "types": ["cafe"],
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert props["Neighborhood"] == {"select": {"name": "Barrio Nuevo"}}
    assert len(fake_claude.calls) == 0


def test_neighborhood_pipeline_rejects_directional_conflict():
    """Pipeline drops neighborhood when selected direction conflicts with address direction."""
    schema = PropertySchema(
        name="Neighborhood",
        type="select",
        options=[
            SelectOption(id="1", name="South Minneapolis", color="blue"),
            SelectOption(id="2", name="Northeast Minneapolis", color="green"),
        ],
    )
    pipeline = NeighborhoodPipeline("Neighborhood", schema)
    fake_claude = _FakeClaude("South Minneapolis", is_new=False)
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Odin Apartments",
                "formattedAddress": "401 1st Ave NE, Minneapolis, MN 55413, USA",
                "neighborhood": None,
                "primaryType": "apartment_complex",
                "types": ["apartment_complex", "point_of_interest"],
                "latitude": 44.9900172,
                "longitude": -93.2557362,
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Neighborhood" not in props


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
