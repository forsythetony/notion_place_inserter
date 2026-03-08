"""Unit tests for cover and icon pipelines (image_resolution stage)."""

from unittest.mock import MagicMock

from app.app_global_pipelines.places_to_visit import (
    ResolveCoverFromGooglePhotosStep,
    ResolveCoverImagePipeline,
    ResolveIconEmojiPipeline,
    ResolveIconEmojiStep,
)
from app.pipeline_lib.context import ContextKeys as CtxKeys, PipelineRunContext
from app.pipeline_lib.orchestration import _run_pipeline


class _FakeGooglePlaces:
    def __init__(self, photo_bytes: bytes | None, photo_url: str | None = None):
        self.photo_bytes = photo_bytes
        self.photo_url = photo_url
        self.get_photo_bytes_calls: list[dict] = []
        self.get_photo_url_calls: list[dict] = []

    def get_photo_bytes(self, photo_name: str, **kwargs) -> bytes | None:
        self.get_photo_bytes_calls.append({"photo_name": photo_name, "kwargs": kwargs})
        return self.photo_bytes

    def get_photo_url(self, photo_name: str, **kwargs) -> str | None:
        self.get_photo_url_calls.append({"photo_name": photo_name, "kwargs": kwargs})
        return self.photo_url


class _FakeNotion:
    def __init__(self, upload_result: dict | None):
        self.upload_result = upload_result
        self.upload_calls: list[dict] = []

    def upload_cover_from_bytes(self, image_bytes: bytes, **kwargs) -> dict | None:
        self.upload_calls.append({"image_bytes_len": len(image_bytes), "kwargs": kwargs})
        return self.upload_result


class _FakeClaude:
    def __init__(self, search_term: str | None):
        self.search_term = search_term
        self.choose_icon_search_term_calls: list[dict] = []

    def choose_icon_search_term_for_place(self, candidate_context: dict) -> str | None:
        self.choose_icon_search_term_calls.append({"candidate_context": candidate_context})
        return self.search_term


class _FakeFreepik:
    def __init__(self, icon_url: str | None):
        self.icon_url = icon_url
        self.get_first_icon_url_calls: list[str] = []

    def get_first_icon_url(self, term: str) -> str | None:
        self.get_first_icon_url_calls.append(term)
        return self.icon_url


def test_cover_pipeline_sets_cover_when_photo_available():
    """Cover pipeline writes COVER_IMAGE when Google returns bytes and Notion upload succeeds."""
    pipeline = ResolveCoverImagePipeline()
    fake_google = _FakeGooglePlaces(b"fake-image-bytes")
    fake_notion = _FakeNotion({"type": "file_upload", "file_upload": {"id": "fu-123"}})
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_google_places_service": fake_google,
            "_notion_service": fake_notion,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Stone Arch Bridge",
                "photos": [{"name": "places/ChIJ123/photos/ABC", "widthPx": 800, "heightPx": 600}],
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    cover = ctx.get(CtxKeys.COVER_IMAGE)
    assert cover is not None
    assert cover["type"] == "file_upload"
    assert cover["file_upload"]["id"] == "fu-123"
    assert len(fake_google.get_photo_bytes_calls) == 1
    assert fake_google.get_photo_bytes_calls[0]["photo_name"] == "places/ChIJ123/photos/ABC"
    assert len(fake_notion.upload_calls) == 1
    assert fake_notion.upload_calls[0]["image_bytes_len"] == 16


def test_cover_pipeline_uses_external_url_in_dry_run():
    """In dry run, cover uses external URL and does not upload to Notion."""
    pipeline = ResolveCoverImagePipeline()
    fake_google = _FakeGooglePlaces(
        photo_bytes=b"fake-image-bytes",
        photo_url="https://example.com/cover.jpg",
    )
    fake_notion = _FakeNotion({"type": "file_upload", "file_upload": {"id": "fu-dry"}})
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_google_places_service": fake_google,
            "_notion_service": fake_notion,
            "_dry_run": True,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Stone Arch Bridge",
                "photos": [{"name": "places/ChIJ123/photos/ABC", "widthPx": 800}],
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    cover = ctx.get(CtxKeys.COVER_IMAGE)
    assert cover is not None
    assert cover["type"] == "external"
    assert cover["external"]["url"] == "https://example.com/cover.jpg"
    assert len(fake_google.get_photo_url_calls) == 1
    assert fake_google.get_photo_url_calls[0]["photo_name"] == "places/ChIJ123/photos/ABC"
    assert len(fake_google.get_photo_bytes_calls) == 0
    assert len(fake_notion.upload_calls) == 0


def test_cover_pipeline_skips_when_no_photos():
    """Cover pipeline does not set COVER_IMAGE when place has no photos."""
    pipeline = ResolveCoverImagePipeline()
    fake_google = _FakeGooglePlaces(b"bytes")
    fake_notion = _FakeNotion({"type": "file_upload", "file_upload": {"id": "x"}})
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_google_places_service": fake_google,
            "_notion_service": fake_notion,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Stone Arch Bridge",
                "photos": [],
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    assert ctx.get(CtxKeys.COVER_IMAGE) is None
    assert len(fake_google.get_photo_bytes_calls) == 0


def test_cover_pipeline_skips_when_get_photo_bytes_returns_none():
    """Cover pipeline does not set COVER_IMAGE when get_photo_bytes fails."""
    pipeline = ResolveCoverImagePipeline()
    fake_google = _FakeGooglePlaces(None)
    fake_notion = _FakeNotion({"type": "file_upload", "file_upload": {"id": "x"}})
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_google_places_service": fake_google,
            "_notion_service": fake_notion,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Stone Arch Bridge",
                "photos": [{"name": "places/X/photos/Y", "widthPx": 800}],
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    assert ctx.get(CtxKeys.COVER_IMAGE) is None
    assert len(fake_google.get_photo_bytes_calls) == 1
    assert len(fake_notion.upload_calls) == 0


def test_cover_pipeline_skips_when_upload_fails():
    """Cover pipeline does not set COVER_IMAGE when Notion upload returns None."""
    pipeline = ResolveCoverImagePipeline()
    fake_google = _FakeGooglePlaces(b"bytes")
    fake_notion = _FakeNotion(None)
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_google_places_service": fake_google,
            "_notion_service": fake_notion,
            CtxKeys.GOOGLE_PLACE: {
                "photos": [{"name": "places/X/photos/Y"}],
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    assert ctx.get(CtxKeys.COVER_IMAGE) is None
    assert len(fake_google.get_photo_bytes_calls) == 1
    assert len(fake_notion.upload_calls) == 1


def test_cover_pipeline_skips_when_no_place_or_google_or_notion():
    """Cover pipeline does nothing when place, Google, or Notion service is missing."""
    pipeline = ResolveCoverImagePipeline()
    fake_google = _FakeGooglePlaces(b"bytes")
    fake_notion = _FakeNotion({"type": "file_upload", "file_upload": {"id": "x"}})

    ctx_no_place = PipelineRunContext(
        run_id="r1",
        initial={"_google_places_service": fake_google, "_notion_service": fake_notion},
    )
    ctx_no_place.set("_global_pipeline_id", "gp")
    ctx_no_place.set("_current_stage_id", "s1")
    ctx_no_place.set("_current_pipeline_id", "p1")
    _run_pipeline(pipeline, ctx_no_place, "r1", "s1")
    assert ctx_no_place.get(CtxKeys.COVER_IMAGE) is None

    ctx_no_google = PipelineRunContext(
        run_id="r2",
        initial={
            "_notion_service": fake_notion,
            CtxKeys.GOOGLE_PLACE: {"photos": [{"name": "places/X/photos/Y"}]},
        },
    )
    ctx_no_google.set("_global_pipeline_id", "gp")
    ctx_no_google.set("_current_stage_id", "s1")
    ctx_no_google.set("_current_pipeline_id", "p1")
    _run_pipeline(pipeline, ctx_no_google, "r2", "s1")
    assert ctx_no_google.get(CtxKeys.COVER_IMAGE) is None

    ctx_no_notion = PipelineRunContext(
        run_id="r3",
        initial={
            "_google_places_service": fake_google,
            CtxKeys.GOOGLE_PLACE: {"photos": [{"name": "places/X/photos/Y"}]},
        },
    )
    ctx_no_notion.set("_global_pipeline_id", "gp")
    ctx_no_notion.set("_current_stage_id", "s1")
    ctx_no_notion.set("_current_pipeline_id", "p1")
    _run_pipeline(pipeline, ctx_no_notion, "r3", "s1")
    assert ctx_no_notion.get(CtxKeys.COVER_IMAGE) is None


def test_icon_pipeline_sets_icon_when_freepik_returns_url():
    """Icon pipeline writes ICON when Claude returns search term and Freepik returns URL."""
    pipeline = ResolveIconEmojiPipeline()
    fake_claude = _FakeClaude("bridge")
    fake_freepik = _FakeFreepik("https://cdn.freepik.com/icon/bridge.png")
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            "_freepik_service": fake_freepik,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Stone Arch Bridge",
                "primaryType": "bridge",
                "types": ["bridge", "landmark"],
                "generativeSummary": "Historic bridge",
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    icon = ctx.get(CtxKeys.ICON)
    assert icon is not None
    assert icon["type"] == "external"
    assert icon["external"]["url"] == "https://cdn.freepik.com/icon/bridge.png"
    assert len(fake_claude.choose_icon_search_term_calls) == 1
    assert fake_claude.choose_icon_search_term_calls[0]["candidate_context"]["displayName"] == "Stone Arch Bridge"
    assert fake_claude.choose_icon_search_term_calls[0]["candidate_context"]["primaryType"] == "bridge"
    assert len(fake_freepik.get_first_icon_url_calls) == 1
    assert fake_freepik.get_first_icon_url_calls[0] == "bridge"


def test_icon_pipeline_skips_when_claude_returns_no_search_term():
    """Icon pipeline does not set ICON when Claude returns None."""
    pipeline = ResolveIconEmojiPipeline()
    fake_claude = _FakeClaude(None)
    fake_freepik = _FakeFreepik("https://example.com/icon.png")
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            "_freepik_service": fake_freepik,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Stone Arch Bridge",
                "primaryType": "bridge",
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    assert ctx.get(CtxKeys.ICON) is None
    assert len(fake_claude.choose_icon_search_term_calls) == 1
    assert len(fake_freepik.get_first_icon_url_calls) == 0


def test_icon_pipeline_skips_when_freepik_returns_no_results():
    """Icon pipeline does not set ICON when Freepik returns None."""
    pipeline = ResolveIconEmojiPipeline()
    fake_claude = _FakeClaude("bridge")
    fake_freepik = _FakeFreepik(None)
    ctx = PipelineRunContext(
        run_id="r1",
        initial={
            "_claude_service": fake_claude,
            "_freepik_service": fake_freepik,
            CtxKeys.GOOGLE_PLACE: {
                "displayName": "Stone Arch Bridge",
                "primaryType": "bridge",
            },
        },
    )
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    assert ctx.get(CtxKeys.ICON) is None
    assert len(fake_claude.choose_icon_search_term_calls) == 1
    assert len(fake_freepik.get_first_icon_url_calls) == 1


def test_icon_pipeline_skips_when_no_place_or_claude_or_freepik():
    """Icon pipeline does nothing when place, Claude, or Freepik service is missing."""
    pipeline = ResolveIconEmojiPipeline()
    fake_claude = _FakeClaude("bridge")
    fake_freepik = _FakeFreepik("https://example.com/icon.png")

    ctx_no_place = PipelineRunContext(
        run_id="r1",
        initial={"_claude_service": fake_claude, "_freepik_service": fake_freepik},
    )
    ctx_no_place.set("_global_pipeline_id", "gp")
    ctx_no_place.set("_current_stage_id", "s1")
    ctx_no_place.set("_current_pipeline_id", "p1")
    _run_pipeline(pipeline, ctx_no_place, "r1", "s1")
    assert ctx_no_place.get(CtxKeys.ICON) is None

    ctx_no_claude = PipelineRunContext(
        run_id="r2",
        initial={
            "_freepik_service": fake_freepik,
            CtxKeys.GOOGLE_PLACE: {"displayName": "Test", "primaryType": "park"},
        },
    )
    ctx_no_claude.set("_global_pipeline_id", "gp")
    ctx_no_claude.set("_current_stage_id", "s1")
    ctx_no_claude.set("_current_pipeline_id", "p1")
    _run_pipeline(pipeline, ctx_no_claude, "r2", "s1")
    assert ctx_no_claude.get(CtxKeys.ICON) is None

    ctx_no_freepik = PipelineRunContext(
        run_id="r3",
        initial={
            "_claude_service": fake_claude,
            CtxKeys.GOOGLE_PLACE: {"displayName": "Test", "primaryType": "park"},
        },
    )
    ctx_no_freepik.set("_global_pipeline_id", "gp")
    ctx_no_freepik.set("_current_stage_id", "s1")
    ctx_no_freepik.set("_current_pipeline_id", "p1")
    _run_pipeline(pipeline, ctx_no_freepik, "r3", "s1")
    assert ctx_no_freepik.get(CtxKeys.ICON) is None
