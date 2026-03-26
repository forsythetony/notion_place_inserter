"""Unit tests for snapshot-driven job execution (p3_pr06)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.job_execution.binding_resolver import resolve_binding, resolve_input_bindings
from app.services.job_execution.job_execution_service import JobExecutionService
from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle
from app.services.job_execution.step_pipeline_log import StepPipelineLog
from app.services.job_execution.handlers import (
    AiPromptHandler,
    AiSelectRelationHandler,
    CacheGetHandler,
    CacheSetHandler,
    DataTransformHandler,
    OptimizeInputClaudeHandler,
    PropertySetHandler,
    SearchIconsHandler,
    TemplaterHandler,
    UploadImageToNotionHandler,
)
from app.services.job_execution.step_runtime_registry import StepRuntimeRegistry
from app.services.job_execution.target_write_adapter import build_notion_properties_payload


def _make_step_handle(step_run_id: str = "sr_test") -> StepExecutionHandle:
    pl = StepPipelineLog(
        run_id="r1",
        job_id="j1",
        stage_id="s1",
        pipeline_id="p1",
        step_id="step1",
        step_template_id="tpl1",
    )
    return StepExecutionHandle(step_run_id=step_run_id, pipeline_log=pl)


async def test_step_execution_handle_isolates_processing_lines():
    """Parallel pipelines: each handle appends only to its own StepPipelineLog."""
    la = StepPipelineLog(
        run_id="r1",
        job_id="j1",
        stage_id="s1",
        pipeline_id="p1",
        step_id="a",
        step_template_id="t1",
    )
    lb = StepPipelineLog(
        run_id="r1",
        job_id="j1",
        stage_id="s1",
        pipeline_id="p2",
        step_id="b",
        step_template_id="t1",
    )
    ha = StepExecutionHandle(step_run_id="sr_a", pipeline_log=la)
    hb = StepExecutionHandle(step_run_id="sr_b", pipeline_log=lb)
    ha.log_processing("line-a")
    hb.log_processing("line-b")
    assert any("line-a" in x for x in la.processing_lines)
    assert any("line-b" in x for x in lb.processing_lines)
    assert not any("line-b" in x for x in la.processing_lines)
    assert not any("line-a" in x for x in lb.processing_lines)


async def test_resolve_signal_ref_trigger_payload():
    """signal_ref trigger.payload.raw_input resolves from trigger_payload."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={"raw_input": "coffee shop"},
    )
    result = resolve_binding(
        {"signal_ref": "trigger.payload.raw_input"},
        ctx,
        {},
    )
    assert result == "coffee shop"


async def test_resolve_signal_ref_trigger_payload_keywords():
    """signal_ref trigger.payload.keywords resolves from trigger_payload."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={"keywords": "coffee shop", "raw_input": "coffee shop"},
    )
    assert (
        resolve_binding({"signal_ref": "trigger.payload.keywords"}, ctx, {})
        == "coffee shop"
    )


async def test_resolve_signal_ref_trigger_payload_keywords_falls_back_to_raw_input():
    """When schema has no keywords, legacy bindings still work via raw_input duplicate."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={
            "imageData": "base64img",
            "coordinates": "0, 0",
            "raw_input": "base64img",
        },
    )
    assert (
        resolve_binding({"signal_ref": "trigger.payload.keywords"}, ctx, {})
        == "base64img"
    )


async def test_resolve_signal_ref_step_output():
    """signal_ref step.step_id.output_name resolves from step_outputs."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    ctx.set_step_output("step_optimize_query", "optimized_query", "Stone Arch Bridge Minneapolis")
    result = resolve_binding(
        {"signal_ref": "step.step_optimize_query.optimized_query"},
        ctx,
        {},
    )
    assert result == "Stone Arch Bridge Minneapolis"


async def test_resolve_signal_ref_step_output_nested_path():
    """signal_ref supports nested paths under a step output dict/list."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    ctx.set_step_output(
        "step_google",
        "selected_place",
        {
            "displayName": "Katz's Delicatessen",
            "addressComponents": [{"longText": "205"}, {"longText": "East Houston Street"}],
        },
    )
    result_name = resolve_binding(
        {"signal_ref": "step.step_google.selected_place.displayName"},
        ctx,
        {},
    )
    result_street = resolve_binding(
        {"signal_ref": "step.step_google.selected_place.addressComponents.1.longText"},
        ctx,
        {},
    )
    assert result_name == "Katz's Delicatessen"
    assert result_street == "East Houston Street"


async def test_resolve_cache_key():
    """cache_key in binding reads from run_cache."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    ctx.run_cache["google_places_response"] = {"places": []}
    result = resolve_binding(
        {"cache_key": "google_places_response"},
        ctx,
        {},
    )
    assert result == {"places": []}


async def test_resolve_cache_key_ref_with_path():
    """cache_key_ref with optional path traverses nested cached value."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx.run_cache["google_places_selected_place"] = {
        "displayName": "Bridge",
        "photos": [{"name": "places/123/photos/abc"}],
    }
    assert (
        resolve_binding(
            {"cache_key_ref": {"cache_key": "google_places_selected_place", "path": "displayName"}},
            ctx,
            {},
        )
        == "Bridge"
    )
    assert (
        resolve_binding(
            {"cache_key_ref": {"cache_key": "google_places_selected_place", "path": "photos.0.name"}},
            ctx,
            {},
        )
        == "places/123/photos/abc"
    )


async def test_resolve_static_value():
    """static_value returns literal."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    result = resolve_binding({"static_value": "literal"}, ctx, {})
    assert result == "literal"


async def test_resolve_target_schema_ref_options():
    """target_schema_ref resolves schema property options."""
    snapshot = {
        "active_schema": {
            "properties": [
                {
                    "id": "prop_tags",
                    "external_property_id": "tags",
                    "options": [
                        {"id": "opt1", "name": "History"},
                        {"id": "opt2", "name": "Landmark"},
                    ],
                },
            ],
        },
    }
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    result = resolve_binding(
        {
            "target_schema_ref": {
                "schema_property_id": "prop_tags",
                "field": "options",
            },
        },
        ctx,
        snapshot,
    )
    assert result == [{"id": "opt1", "name": "History"}, {"id": "opt2", "name": "Landmark"}]


async def test_resolve_input_bindings_multiple():
    """resolve_input_bindings resolves all bindings."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={"raw_input": "pizza"},
    )
    ctx.set_step_output("step_a", "value", "resolved")
    bindings = {
        "query": {"signal_ref": "trigger.payload.raw_input"},
        "other": {"signal_ref": "step.step_a.value"},
    }
    result = resolve_input_bindings(bindings, ctx, {})
    assert result["query"] == "pizza"
    assert result["other"] == "resolved"


async def test_cache_set_handler_stores_in_run_cache():
    """CacheSetHandler stores value in run_cache."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = CacheSetHandler()
    await handler.execute(
        step_id="step_cache",
        config={"cache_key": "my_key"},
        input_bindings={"value": {"signal_ref": "trigger.payload.raw_input"}},
        resolved_inputs={"value": "stored_value"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert ctx.run_cache.get("my_key") == "stored_value"


async def test_cache_get_handler_returns_cached_value():
    """CacheGetHandler returns value from run_cache."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx.run_cache["my_key"] = "cached"
    handler = CacheGetHandler()
    result = await handler.execute(
        step_id="step_get",
        config={"cache_key": "my_key"},
        input_bindings={},
        resolved_inputs={},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert result == {"value": "cached"}


async def test_property_set_handler_stores_in_properties():
    """PropertySetHandler stores value in ctx.properties."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = PropertySetHandler()
    await handler.execute(
        step_id="step_prop",
        config={"schema_property_id": "prop_tags"},
        input_bindings={"value": {}},
        resolved_inputs={"value": ["History", "Landmark"]},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert ctx.properties.get("prop_tags") == ["History", "Landmark"]


async def test_property_set_handler_stores_in_page_metadata_cover():
    """PropertySetHandler with target_kind=page_metadata sets ctx.cover."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = PropertySetHandler()
    payload = {"type": "external", "external": {"url": "https://example.com/cover.jpg"}}
    await handler.execute(
        step_id="step_cover",
        config={"target_kind": "page_metadata", "target_field": "cover_image"},
        input_bindings={"value": {}},
        resolved_inputs={"value": payload},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert ctx.cover == payload


async def test_property_set_handler_stores_in_page_metadata_icon():
    """PropertySetHandler with target_kind=page_metadata sets ctx.icon."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = PropertySetHandler()
    payload = {"type": "file_upload", "file_upload": {"id": "fu-123"}}
    await handler.execute(
        step_id="step_icon",
        config={"target_kind": "page_metadata", "target_field": "icon_image"},
        input_bindings={"value": {}},
        resolved_inputs={"value": payload},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert ctx.icon == payload


async def test_property_set_handler_page_metadata_converts_url_string():
    """PropertySetHandler converts URL string to external payload for page_metadata."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = PropertySetHandler()
    await handler.execute(
        step_id="step_cover",
        config={"target_kind": "page_metadata", "target_field": "cover_image"},
        input_bindings={"value": {}},
        resolved_inputs={"value": "https://example.com/img.png"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert ctx.cover == {"type": "external", "external": {"url": "https://example.com/img.png"}}


async def test_data_transform_handler_extract_key():
    """DataTransformHandler extracts value at source_path."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = DataTransformHandler()
    value = {"photos": [{"name": "places/abc/photos/xyz"}, {"name": "places/def/photos/uvw"}]}
    result = await handler.execute(
        step_id="step_transform",
        config={"operation": "extract_key", "source_path": "photos[0].name"},
        input_bindings={"value": {}},
        resolved_inputs={"value": value},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert result["transformed_value"] == "places/abc/photos/xyz"


async def test_data_transform_handler_returns_fallback_when_path_missing():
    """DataTransformHandler returns fallback_value when path missing."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = DataTransformHandler()
    result = await handler.execute(
        step_id="step_transform",
        config={
            "operation": "extract_key",
            "source_path": "photos[0].url",
            "fallback_value": "default.jpg",
        },
        input_bindings={"value": {}},
        resolved_inputs={"value": {"photos": [{"name": "x"}]}},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert result["transformed_value"] == "default.jpg"


async def test_templater_handler_renders_template():
    """TemplaterHandler replaces {{key}} placeholders with values."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = TemplaterHandler()
    result = await handler.execute(
        step_id="step_templater",
        config={
            "template": "{{latitude}}, {{longitude}}",
            "values": {
                "latitude": {"static_value": 44.9778},
                "longitude": {"static_value": -93.2650},
            },
        },
        input_bindings={},
        resolved_inputs={},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert result["rendered_value"] == "44.9778, -93.265"  # float str() drops trailing zero


async def test_templater_handler_signal_ref_resolution():
    """TemplaterHandler resolves signal_ref in values (e.g. from step output or cache_get)."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx.set_step_output(
        "step_cache_get_place",
        "value",
        {"latitude": 19.43, "longitude": -99.16},
    )
    handler = TemplaterHandler()
    result = await handler.execute(
        step_id="step_templater",
        config={
            "template": "{{latitude}}, {{longitude}}",
            "values": {
                "latitude": {"signal_ref": "step.step_cache_get_place.value.latitude"},
                "longitude": {"signal_ref": "step.step_cache_get_place.value.longitude"},
            },
        },
        input_bindings={},
        resolved_inputs={},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert result["rendered_value"] == "19.43, -99.16"


async def test_templater_handler_cache_key_ref_resolution():
    """TemplaterHandler resolves cache_key in values (flat cached value)."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx.run_cache["lat"] = 44.9778
    ctx.run_cache["lng"] = -93.2650
    handler = TemplaterHandler()
    result = await handler.execute(
        step_id="step_templater",
        config={
            "template": "{{latitude}}, {{longitude}}",
            "values": {
                "latitude": {"cache_key": "lat"},
                "longitude": {"cache_key": "lng"},
            },
        },
        input_bindings={},
        resolved_inputs={},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert result["rendered_value"] == "44.9778, -93.265"  # float str() drops trailing zero


async def test_templater_handler_missing_key_renders_empty():
    """TemplaterHandler renders empty string for missing placeholder keys."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = TemplaterHandler()
    result = await handler.execute(
        step_id="step_templater",
        config={
            "template": "{{a}}-{{b}}-{{c}}",
            "values": {"a": {"static_value": "x"}, "c": {"static_value": "z"}},
        },
        input_bindings={},
        resolved_inputs={},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert result["rendered_value"] == "x--z"


async def test_templater_handler_non_string_values_stringify():
    """TemplaterHandler stringifies non-string values (int, float, dict)."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = TemplaterHandler()
    result = await handler.execute(
        step_id="step_templater",
        config={
            "template": "{{n}} {{f}}",
            "values": {
                "n": {"static_value": 42},
                "f": {"static_value": 3.14},
            },
        },
        input_bindings={},
        resolved_inputs={},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert result["rendered_value"] == "42 3.14"


async def test_step_runtime_registry_get_returns_templater_handler():
    """StepRuntimeRegistry returns TemplaterHandler for step_template_templater."""
    reg = StepRuntimeRegistry()
    reg.register("step_template_templater", TemplaterHandler)
    handler = reg.get("step_template_templater")
    assert handler is not None
    assert isinstance(handler, TemplaterHandler)


async def test_search_icons_handler_returns_url_when_freepik_available():
    """SearchIconsHandler returns image_url from Freepik when service available."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx.owner_user_id = "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde"
    ctx._services["freepik"] = MagicMock()
    ctx._services["freepik"].get_first_icon_url.return_value = "https://cdn.freepik.com/icon.png"
    usage = MagicMock()
    usage.record_external_api_call = AsyncMock()
    ctx._services["usage_accounting"] = usage
    handler = SearchIconsHandler()
    result = await handler.execute(
        step_id="step_search",
        config={},
        input_bindings={"query": {}},
        resolved_inputs={"query": "coffee shop"},
        ctx=ctx,
        step_handle=_make_step_handle("step_run_1"),
        snapshot={},
    )
    assert result["image_url"] == "https://cdn.freepik.com/icon.png"
    usage.record_external_api_call.assert_awaited_once()
    call_kw = usage.record_external_api_call.call_args.kwargs
    assert call_kw["provider"] == "freepik"
    assert call_kw["operation"] == "search_icons"
    assert call_kw["job_run_id"] == "r1"
    assert call_kw["owner_user_id"] == ctx.owner_user_id
    assert call_kw["step_run_id"] == "step_run_1"


async def test_search_icons_handler_returns_none_when_no_freepik():
    """SearchIconsHandler returns None when Freepik service not configured."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = SearchIconsHandler()
    result = await handler.execute(
        step_id="step_search",
        config={},
        input_bindings={"query": {}},
        resolved_inputs={"query": "bridge"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert result["image_url"] is None


async def test_search_icons_handler_skips_usage_when_query_empty():
    """SearchIconsHandler does not call Freepik or record usage for an empty query."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx.owner_user_id = "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde"
    freepik = MagicMock()
    ctx._services["freepik"] = freepik
    usage = MagicMock()
    ctx._services["usage_accounting"] = usage
    handler = SearchIconsHandler()
    result = await handler.execute(
        step_id="step_search",
        config={},
        input_bindings={"query": {}},
        resolved_inputs={"query": "   "},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert result["image_url"] is None
    freepik.get_first_icon_url.assert_not_called()
    usage.record_external_api_call.assert_not_called()


async def test_upload_image_to_notion_handler_dry_run_passthrough_external_url():
    """UploadImageToNotionHandler returns external payload in dry-run for URL input."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx.dry_run = True
    ctx._services["notion"] = MagicMock()
    ctx._services["google_places"] = MagicMock()
    handler = UploadImageToNotionHandler()
    with patch(
        "app.services.job_execution.handlers.upload_image_to_notion._fetch_image_bytes",
        return_value=None,
    ):
        result = await handler.execute(
            step_id="step_upload",
            config={},
            input_bindings={"value": {}},
            resolved_inputs={"value": "https://example.com/image.jpg"},
            ctx=ctx,
            step_handle=_make_step_handle(),
            snapshot={},
        )
    assert result["notion_image_url"] == {
        "type": "external",
        "external": {"url": "https://example.com/image.jpg"},
    }


async def test_upload_image_to_notion_handler_dry_run_never_uploads_when_bytes_available():
    """Dry-run mode never uploads image bytes to Notion."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx.dry_run = True
    notion = MagicMock()
    ctx._services["notion"] = notion
    ctx._services["google_places"] = MagicMock()
    handler = UploadImageToNotionHandler()
    with patch(
        "app.services.job_execution.handlers.upload_image_to_notion._fetch_image_bytes",
        return_value=b"fake-image-bytes",
    ) as fetch_mock:
        result = await handler.execute(
            step_id="step_upload",
            config={},
            input_bindings={"value": {}},
            resolved_inputs={"value": "https://example.com/image.jpg"},
            ctx=ctx,
            step_handle=_make_step_handle(),
            snapshot={},
        )
    assert result["notion_image_url"] == {
        "type": "external",
        "external": {"url": "https://example.com/image.jpg"},
    }
    fetch_mock.assert_not_called()
    notion.upload_cover_from_bytes.assert_not_called()


async def test_upload_image_to_notion_handler_dry_run_google_photo_uses_external_url_only():
    """Dry-run Google photo path returns external URL and skips byte upload."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx.dry_run = True
    notion = MagicMock()
    google = MagicMock()
    google.get_photo_url.return_value = "https://example.com/google-photo.jpg"
    google.get_photo_bytes.return_value = b"bytes-that-should-not-be-used"
    ctx._services["notion"] = notion
    ctx._services["google_places"] = google
    handler = UploadImageToNotionHandler()

    result = await handler.execute(
        step_id="step_upload",
        config={},
        input_bindings={"value": {}},
        resolved_inputs={"value": "places/abc/photos/def"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )

    assert result["notion_image_url"] == {
        "type": "external",
        "external": {"url": "https://example.com/google-photo.jpg"},
    }
    google.get_photo_url.assert_called_once_with("places/abc/photos/def")
    google.get_photo_bytes.assert_not_called()
    notion.upload_cover_from_bytes.assert_not_called()


async def test_upload_image_to_notion_handler_uses_oauth_token_for_upload_when_available():
    """UploadImageToNotionHandler passes owner OAuth token to Notion upload."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
        owner_user_id="owner-123",
    )
    notion = MagicMock()
    notion.upload_cover_from_bytes.return_value = {"type": "file_upload", "file_upload": {"id": "fu-1"}}
    ctx._services["notion"] = notion
    ctx._services["google_places"] = MagicMock()
    ctx._services["get_notion_token"] = MagicMock(return_value="oauth-token-abc")
    handler = UploadImageToNotionHandler()

    with patch(
        "app.services.job_execution.handlers.upload_image_to_notion._fetch_image_bytes",
        return_value=b"fake-image-bytes",
    ):
        result = await handler.execute(
            step_id="step_upload",
            config={},
            input_bindings={"value": {}},
            resolved_inputs={"value": "https://example.com/image.jpg"},
            ctx=ctx,
            step_handle=_make_step_handle(),
            snapshot={},
        )

    assert result["notion_image_url"] == {"type": "file_upload", "file_upload": {"id": "fu-1"}}
    notion.upload_cover_from_bytes.assert_called_once_with(
        b"fake-image-bytes",
        filename="image.jpg",
        content_type="image/jpeg",
        access_token="oauth-token-abc",
    )


async def test_upload_image_to_notion_handler_logs_fallback_when_oauth_unavailable():
    """UploadImageToNotionHandler logs fallback when owner_user_id set but token_getter returns None."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
        owner_user_id="owner-123",
    )
    notion = MagicMock()
    notion.upload_cover_from_bytes.return_value = {"type": "file_upload", "file_upload": {"id": "fu-1"}}
    ctx._services["notion"] = notion
    ctx._services["google_places"] = MagicMock()
    ctx._services["get_notion_token"] = MagicMock(return_value=None)
    handler = UploadImageToNotionHandler()

    with patch(
        "app.services.job_execution.handlers.upload_image_to_notion._fetch_image_bytes",
        return_value=b"fake-image-bytes",
    ):
        with patch("app.services.job_execution.handlers.upload_image_to_notion.logger") as mock_logger:
            result = await handler.execute(
                step_id="step_upload",
                config={},
                input_bindings={"value": {}},
                resolved_inputs={"value": "https://example.com/image.jpg"},
                ctx=ctx,
                step_handle=_make_step_handle(),
                snapshot={},
            )

    assert result["notion_image_url"] == {"type": "file_upload", "file_upload": {"id": "fu-1"}}
    call_kwargs = notion.upload_cover_from_bytes.call_args.kwargs
    assert "access_token" not in call_kwargs
    mock_logger.warning.assert_called()
    fallback_calls = [c for c in mock_logger.warning.call_args_list if "notion_upload_fallback_to_global_token" in str(c)]
    assert len(fallback_calls) == 1
    call_str = str(fallback_calls[0])
    assert "owner-123" in call_str
    assert "oauth_token_unavailable" in call_str


async def test_optimize_input_claude_handler_returns_optimized_query():
    """OptimizeInputClaudeHandler returns optimized_query (or passthrough when no Claude)."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    handler = OptimizeInputClaudeHandler()
    result = await handler.execute(
        step_id="step_opt",
        config={"prompt": "Rewrite"},
        input_bindings={"query": {}},
        resolved_inputs={"query": "coffee shop"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert "optimized_query" in result
    assert result["optimized_query"] == "coffee shop"  # no Claude, passthrough


async def test_optimize_input_claude_handler_uses_schema_when_linked_step_consumes_output():
    """When optimized_query is wired to a step with query_schema, uses rewrite_query_for_target."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    claude = MagicMock()
    claude.rewrite_query_for_target.return_value = "Stone Arch Bridge Minneapolis MN"
    claude.get_last_usage.return_value = {"input_tokens": 10, "output_tokens": 5}
    ctx._services["claude"] = claude

    snapshot = {
        "job": {
            "stages": [
                {
                    "pipelines": [
                        {
                            "steps": [
                                {"id": "step_opt", "step_template_id": "step_template_optimize_input_claude"},
                                {
                                    "id": "step_google_places_lookup",
                                    "step_template_id": "step_template_google_places_lookup",
                                    "input_bindings": {
                                        "query": {"signal_ref": "step.step_opt.optimized_query"},
                                    },
                                },
                            ],
                        },
                    ],
                },
            ],
        },
        "step_templates": {
            "step_template_google_places_lookup": {
                "query_schema": {
                    "description": "Google Places text query",
                    "hints": ["Include place name and location"],
                },
            },
        },
    }

    handler = OptimizeInputClaudeHandler()
    result = await handler.execute(
        step_id="step_opt",
        config={},
        input_bindings={"query": {}},
        resolved_inputs={"query": "stone arch bridge minneapolis"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot=snapshot,
    )
    assert result["optimized_query"] == "Stone Arch Bridge Minneapolis MN"
    claude.rewrite_query_for_target.assert_called_once()
    call_kw = claude.rewrite_query_for_target.call_args.kwargs
    assert call_kw["query_schema"]["description"] == "Google Places text query"
    claude.rewrite_place_query.assert_not_called()


async def test_optimize_input_claude_handler_falls_back_to_rewrite_place_query_when_no_schema():
    """When no linked step or no query_schema, uses rewrite_place_query."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    claude = MagicMock()
    claude.rewrite_place_query.return_value = "coffee shop"
    claude.get_last_usage.return_value = {"input_tokens": 10, "output_tokens": 5}
    ctx._services["claude"] = claude

    handler = OptimizeInputClaudeHandler()
    result = await handler.execute(
        step_id="step_opt",
        config={},
        input_bindings={"query": {}},
        resolved_inputs={"query": "coffee shop"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert result["optimized_query"] == "coffee shop"
    claude.rewrite_place_query.assert_called_once_with("coffee shop")
    claude.rewrite_query_for_target.assert_not_called()


async def test_optimize_input_claude_handler_include_target_query_schema_false_skips_schema():
    """When include_target_query_schema is false, uses rewrite_place_query even if linked step exists."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    claude = MagicMock()
    claude.rewrite_place_query.return_value = "Stone Arch Bridge"
    claude.get_last_usage.return_value = {"input_tokens": 10, "output_tokens": 5}
    ctx._services["claude"] = claude

    snapshot = {
        "job": {
            "stages": [
                {
                    "pipelines": [
                        {
                            "steps": [
                                {"id": "step_opt", "step_template_id": "step_template_optimize_input_claude"},
                                {
                                    "id": "step_google_places_lookup",
                                    "step_template_id": "step_template_google_places_lookup",
                                    "input_bindings": {
                                        "query": {"signal_ref": "step.step_opt.optimized_query"},
                                    },
                                },
                            ],
                        },
                    ],
                },
            ],
        },
        "step_templates": {
            "step_template_google_places_lookup": {
                "query_schema": {"description": "Google Places", "hints": []},
            },
        },
    }

    handler = OptimizeInputClaudeHandler()
    result = await handler.execute(
        step_id="step_opt",
        config={"include_target_query_schema": False},
        input_bindings={"query": {}},
        resolved_inputs={"query": "stone arch bridge"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot=snapshot,
    )
    assert result["optimized_query"] == "Stone Arch Bridge"
    claude.rewrite_place_query.assert_called_once()
    claude.rewrite_query_for_target.assert_not_called()


async def test_optimize_input_claude_handler_linked_step_id_override():
    """When linked_step_id is set in config, uses that step for schema lookup."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    claude = MagicMock()
    claude.rewrite_query_for_target.return_value = "bridge"
    claude.get_last_usage.return_value = {"input_tokens": 10, "output_tokens": 5}
    ctx._services["claude"] = claude

    snapshot = {
        "job": {
            "stages": [
                {
                    "pipelines": [
                        {
                            "steps": [
                                {"id": "step_opt", "step_template_id": "step_template_optimize_input_claude"},
                                {
                                    "id": "step_icon_search",
                                    "step_template_id": "step_template_search_icons",
                                    "input_bindings": {
                                        "query": {"signal_ref": "step.step_opt.optimized_query"},
                                    },
                                },
                            ],
                        },
                    ],
                },
            ],
        },
        "step_templates": {
            "step_template_search_icons": {
                "query_schema": {
                    "description": "Short Freepik icon keyword",
                    "hints": ["1-3 words only"],
                },
            },
        },
    }

    handler = OptimizeInputClaudeHandler()
    result = await handler.execute(
        step_id="step_opt",
        config={"linked_step_id": "step_icon_search"},
        input_bindings={"query": {}},
        resolved_inputs={"query": "Stone Arch Bridge"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot=snapshot,
    )
    assert result["optimized_query"] == "bridge"
    claude.rewrite_query_for_target.assert_called_once()
    call_kw = claude.rewrite_query_for_target.call_args.kwargs
    assert call_kw["query_schema"]["description"] == "Short Freepik icon keyword"


async def test_ai_prompt_handler_returns_value_when_claude_available():
    """AiPromptHandler returns value from Claude prompt_completion when service available."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    claude = MagicMock()
    claude.prompt_completion.return_value = "A charming café in downtown."
    ctx._services["claude"] = claude
    handler = AiPromptHandler()
    result = await handler.execute(
        step_id="step_ai_prompt",
        config={"prompt": "Rewrite into a travel note."},
        input_bindings={"value": {}},
        resolved_inputs={"value": {"displayName": "Joe's Coffee", "formattedAddress": "123 Main St"}},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert result["value"] == "A charming café in downtown."
    claude.prompt_completion.assert_called_once_with(
        prompt="Rewrite into a travel note.",
        value={"displayName": "Joe's Coffee", "formattedAddress": "123 Main St"},
        max_tokens=1024,
    )


async def test_ai_prompt_handler_returns_empty_when_no_claude():
    """AiPromptHandler returns empty string when Claude service not configured."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    handler = AiPromptHandler()
    result = await handler.execute(
        step_id="step_ai_prompt",
        config={"prompt": "Rewrite."},
        input_bindings={"value": {}},
        resolved_inputs={"value": "input text"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={},
    )
    assert result["value"] == ""


async def test_step_runtime_registry_get_returns_handler():
    """StepRuntimeRegistry returns handler for registered step_template_id."""
    from app.services.job_execution.handlers import CacheSetHandler

    reg = StepRuntimeRegistry()
    reg.register("step_template_cache_set", CacheSetHandler)
    handler = reg.get("step_template_cache_set")
    assert handler is not None
    assert isinstance(handler, CacheSetHandler)


async def test_step_runtime_registry_get_unknown_returns_none():
    """StepRuntimeRegistry returns None for unknown step_template_id."""
    reg = StepRuntimeRegistry()
    assert reg.get("step_template_unknown") is None


async def test_build_notion_properties_payload_multi_select():
    """build_notion_properties_payload formats multi_select from list."""
    ctx_properties = {"prop_tags": ["History", "Landmark"]}
    active_schema = {
        "properties": [
            {
                "id": "prop_tags",
                "external_property_id": "tags",
                "property_type": "multi_select",
                "options": [{"id": "o1", "name": "History"}, {"id": "o2", "name": "Landmark"}],
            },
        ],
    }
    result = build_notion_properties_payload(ctx_properties, active_schema)
    assert "tags" in result
    assert result["tags"]["multi_select"] == [{"name": "History"}, {"name": "Landmark"}]


async def test_build_notion_properties_payload_relation():
    """build_notion_properties_payload formats relation from list of page IDs."""
    ctx_properties = {"prop_location": [{"id": "page-uuid-123"}]}
    active_schema = {
        "properties": [
            {
                "id": "prop_location",
                "external_property_id": "Location",
                "property_type": "relation",
            },
        ],
    }
    result = build_notion_properties_payload(ctx_properties, active_schema)
    assert "Location" in result
    assert result["Location"]["relation"] == [{"id": "page-uuid-123"}]


async def test_ai_select_relation_handler_no_match_returns_empty():
    """AiSelectRelationHandler returns empty relation when no Claude or no match."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx._services["notion"] = MagicMock()
    ctx._services["notion"].client = MagicMock()
    ctx._services["notion"].client.data_sources.query.return_value = {
        "results": [
            {"object": "page", "id": "loc-1", "properties": {"Name": {"type": "title", "title": [{"plain_text": "Minneapolis"}]}}},
        ],
        "has_more": False,
    }
    handler = AiSelectRelationHandler()
    result = await handler.execute(
        step_id="step_ai_select",
        config={"related_db": "target_locations", "key_lookup": "title"},
        input_bindings={"source_value": {}},
        resolved_inputs={"source_value": {"displayName": "Stone Arch Bridge", "formattedAddress": "Minneapolis, MN"}},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={"targets": {"target_locations": {"external_target_id": "ds-locations"}}},
    )
    assert result["selected_page_pointer"] is None or result["selected_relation"] == []
    assert "selected_relation" in result


async def test_ai_select_relation_handler_selects_match_when_claude_returns_id():
    """AiSelectRelationHandler returns selected_relation when Claude picks a match."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx._services["notion"] = MagicMock()
    ctx._services["notion"].client = MagicMock()
    ctx._services["notion"].client.data_sources.query.return_value = {
        "results": [
            {"object": "page", "id": "loc-1", "properties": {"Name": {"type": "title", "title": [{"plain_text": "Minneapolis"}]}}},
        ],
        "has_more": False,
    }
    claude = MagicMock()
    claude.choose_best_relation_from_candidates.return_value = "loc-1"
    ctx._services["claude"] = claude
    handler = AiSelectRelationHandler()
    result = await handler.execute(
        step_id="step_ai_select",
        config={"related_db": "target_locations", "key_lookup": "title"},
        input_bindings={"source_value": {}},
        resolved_inputs={"source_value": {"displayName": "Stone Arch Bridge", "formattedAddress": "Minneapolis, MN"}},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={"targets": {"target_locations": {"external_target_id": "ds-locations"}}},
    )
    assert result["selected_relation"] == [{"id": "loc-1"}]
    assert result["selected_page_pointer"] == {"id": "loc-1"}


async def test_ai_select_relation_prefers_get_data_source_id_over_external_target_id():
    """AiSelectRelationHandler prefers NotionService.get_data_source_id(display_name) when available."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    notion = MagicMock()
    notion.get_data_source_id.return_value = "ds-from-display-name"
    notion.client = MagicMock()
    notion.client.data_sources.query.return_value = {
        "results": [
            {"object": "page", "id": "loc-1", "properties": {"Name": {"type": "title", "title": [{"plain_text": "Twin Cities, MN"}]}}},
        ],
        "has_more": False,
    }
    ctx._services["notion"] = notion
    claude = MagicMock()
    claude.choose_best_relation_from_candidates.return_value = "loc-1"
    ctx._services["claude"] = claude
    handler = AiSelectRelationHandler()
    result = await handler.execute(
        step_id="step_ai_select",
        config={"related_db": "target_locations", "key_lookup": "title"},
        input_bindings={"source_value": {}},
        resolved_inputs={"source_value": "1401 West River Rd N, Minneapolis, MN 55411, USA"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={
            "targets": {
                "target_locations": {
                    "display_name": "Locations",
                    "external_target_id": "544d5797-9344-4258-aed6-1f72e66b6927",
                }
            }
        },
    )
    assert result["selected_relation"] == [{"id": "loc-1"}]
    notion.get_data_source_id.assert_called_once_with("Locations")
    notion.client.data_sources.query.assert_called_once()
    call_kwargs = notion.client.data_sources.query.call_args.kwargs
    assert call_kwargs["data_source_id"] == "ds-from-display-name"


async def test_ai_select_relation_returns_empty_on_query_failure():
    """AiSelectRelationHandler returns empty relation when Notion query fails."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    notion = MagicMock()
    notion.get_data_source_id.return_value = "ds-123"
    notion.client = MagicMock()
    notion.client.data_sources.query.side_effect = Exception("Could not find database with ID")
    ctx._services["notion"] = notion
    handler = AiSelectRelationHandler()
    result = await handler.execute(
        step_id="step_ai_select",
        config={"related_db": "target_locations", "key_lookup": "title"},
        input_bindings={"source_value": {}},
        resolved_inputs={"source_value": "Minneapolis, MN"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={"targets": {"target_locations": {"display_name": "Locations"}}},
    )
    assert result["selected_relation"] == []
    assert result["selected_page_pointer"] is None


async def test_ai_select_relation_accepts_address_only_input():
    """AiSelectRelationHandler accepts address string (e.g. from DataTransform) and passes to Claude."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    notion = MagicMock()
    notion.get_data_source_id.return_value = "ds-123"
    notion.client = MagicMock()
    notion.client.data_sources.query.return_value = {
        "results": [
            {"object": "page", "id": "loc-twin", "properties": {"Name": {"type": "title", "title": [{"plain_text": "Twin Cities, MN"}]}}},
        ],
        "has_more": False,
    }
    ctx._services["notion"] = notion
    claude = MagicMock()
    claude.choose_best_relation_from_candidates.return_value = "loc-twin"
    ctx._services["claude"] = claude
    handler = AiSelectRelationHandler()
    result = await handler.execute(
        step_id="step_ai_select",
        config={"related_db": "target_locations", "key_lookup": "title"},
        input_bindings={"source_value": {}},
        resolved_inputs={"source_value": "1401 West River Rd N, Minneapolis, MN 55411, USA"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={"targets": {"target_locations": {"display_name": "Locations"}}},
    )
    assert result["selected_relation"] == [{"id": "loc-twin"}]
    claude.choose_best_relation_from_candidates.assert_called_once()
    call_kwargs = claude.choose_best_relation_from_candidates.call_args.kwargs
    assert call_kwargs["source_context"] == {"value": "1401 West River Rd N, Minneapolis, MN 55411, USA"}


async def test_ai_select_relation_uses_valid_filter_properties_from_data_source_schema():
    """AiSelectRelationHandler uses only schema-valid filter_properties."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    notion = MagicMock()
    notion.get_data_source_id.return_value = "ds-123"
    notion.client = MagicMock()
    notion.client.data_sources.retrieve.return_value = {
        "properties": {
            "Name": {"id": "title", "type": "title"},
            "Region": {"id": "abc123", "type": "rich_text"},
        }
    }
    notion.client.data_sources.query.return_value = {
        "results": [
            {"object": "page", "id": "loc-mpls", "properties": {"Name": {"type": "title", "title": [{"plain_text": "Minneapolis"}]}}},
        ],
        "has_more": False,
    }
    ctx._services["notion"] = notion
    claude = MagicMock()
    claude.choose_best_relation_from_candidates.return_value = "loc-mpls"
    ctx._services["claude"] = claude
    handler = AiSelectRelationHandler()

    result = await handler.execute(
        step_id="step_ai_select",
        config={"related_db": "target_locations", "key_lookup": "title"},
        input_bindings={"source_value": {}},
        resolved_inputs={"source_value": "Minneapolis, MN"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={"targets": {"target_locations": {"display_name": "Locations"}}},
    )

    assert result["selected_relation"] == [{"id": "loc-mpls"}]
    call_kwargs = notion.client.data_sources.query.call_args.kwargs
    assert call_kwargs["data_source_id"] == "ds-123"
    assert call_kwargs["filter_properties"] == ["title", "Name"]


async def test_ai_select_relation_retries_without_filter_properties_on_validation_error():
    """AiSelectRelationHandler retries unfiltered query when filter_properties is rejected."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    notion = MagicMock()
    notion.get_data_source_id.return_value = "ds-123"
    notion.client = MagicMock()
    notion.client.data_sources.retrieve.return_value = {
        "properties": {
            "Name": {"id": "title", "type": "title"},
        }
    }
    notion.client.data_sources.query.side_effect = [
        Exception(
            "The provided `filter_properties` contains an invalid attribute: Title."
        ),
        {
            "results": [
                {"object": "page", "id": "loc-twin", "properties": {"Name": {"type": "title", "title": [{"plain_text": "Twin Cities"}]}}},
            ],
            "has_more": False,
        },
    ]
    ctx._services["notion"] = notion
    claude = MagicMock()
    claude.choose_best_relation_from_candidates.return_value = "loc-twin"
    ctx._services["claude"] = claude
    handler = AiSelectRelationHandler()

    result = await handler.execute(
        step_id="step_ai_select",
        config={"related_db": "target_locations", "key_lookup": "title"},
        input_bindings={"source_value": {}},
        resolved_inputs={"source_value": "Minneapolis, MN"},
        ctx=ctx,
        step_handle=_make_step_handle(),
        snapshot={"targets": {"target_locations": {"display_name": "Locations"}}},
    )

    assert result["selected_relation"] == [{"id": "loc-twin"}]
    assert notion.client.data_sources.query.call_count == 2
    first_kwargs = notion.client.data_sources.query.call_args_list[0].kwargs
    second_kwargs = notion.client.data_sources.query.call_args_list[1].kwargs
    assert first_kwargs["filter_properties"] == ["title", "Name"]
    assert "filter_properties" not in second_kwargs


async def test_execute_snapshot_run_synthesizes_schema_when_missing():
    """When active_schema is missing, runtime synthesizes schema from Notion and writes props."""
    notion = MagicMock()
    notion.get_raw_schema_for_sync.return_value = (
        "ds-123",
        {
            "Tags": {
                "id": "tags",
                "type": "multi_select",
                "multi_select": {
                    "options": [
                        {"id": "o1", "name": "History", "color": "blue"},
                        {"id": "o2", "name": "Landmark", "color": "green"},
                    ]
                },
            }
        },
    )
    notion.create_page.return_value = {"id": "page-1", "object": "page"}
    svc = JobExecutionService(notion_service=notion, dry_run=False)

    snapshot = {
        "job": {
            "stages": [
                {
                    "id": "stage_property_setting",
                    "sequence": 1,
                    "pipeline_run_mode": "sequential",
                    "pipelines": [
                        {
                            "id": "pipeline_tags",
                            "sequence": 1,
                            "steps": [
                                {
                                    "id": "step_property_set_tags",
                                    "step_template_id": "step_template_property_set",
                                    "sequence": 1,
                                    "input_bindings": {
                                        "value": {"static_value": ["History", "Landmark"]}
                                    },
                                    "config": {
                                        "schema_property_id": "prop_tags",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        "target": {
            "display_name": "Places to Visit",
            "external_target_id": "ds-123",
        },
        "active_schema": None,
    }

    result = await svc.execute_snapshot_run(
        snapshot=snapshot,
        run_id="run-1",
        job_id="job-1",
        trigger_payload={"raw_input": "katz deli in new york city"},
    )

    assert result["id"] == "page-1"
    notion.create_page.assert_called_once()
    call_kwargs = notion.create_page.call_args.kwargs
    assert call_kwargs["data_source_id"] == "ds-123"
    assert "tags" in call_kwargs["properties"]
    assert call_kwargs["properties"]["tags"]["multi_select"] == [
        {"name": "History"},
        {"name": "Landmark"},
    ]


async def test_execute_snapshot_run_dry_run_delegates_to_notion_service():
    """Dry-run mode still calls NotionService.create_page (service handles dry-run behavior)."""
    notion = MagicMock()
    notion.create_page.return_value = {"mode": "dry_run", "id": None, "page_id": None}
    svc = JobExecutionService(notion_service=notion, dry_run=True)

    snapshot = {
        "job": {
            "stages": [
                {
                    "id": "stage_property_setting",
                    "sequence": 1,
                    "pipeline_run_mode": "sequential",
                    "pipelines": [
                        {
                            "id": "pipeline_tags",
                            "sequence": 1,
                            "steps": [
                                {
                                    "id": "step_property_set_tags",
                                    "step_template_id": "step_template_property_set",
                                    "sequence": 1,
                                    "input_bindings": {
                                        "value": {"static_value": ["History", "Landmark"]}
                                    },
                                    "config": {
                                        "schema_property_id": "prop_tags",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        "target": {
            "display_name": "Places to Visit",
            "external_target_id": "ds-123",
        },
        "active_schema": {
            "properties": [
                {
                    "id": "prop_tags",
                    "external_property_id": "tags",
                    "property_type": "multi_select",
                    "options": [
                        {"id": "o1", "name": "History"},
                        {"id": "o2", "name": "Landmark"},
                    ],
                },
            ],
        },
    }

    result = await svc.execute_snapshot_run(
        snapshot=snapshot,
        run_id="run-1",
        job_id="job-1",
        trigger_payload={"raw_input": "katz deli in new york city"},
    )

    assert result["mode"] == "dry_run"
    notion.create_page.assert_called_once()
    call_kwargs = notion.create_page.call_args.kwargs
    assert call_kwargs["data_source_id"] == "ds-123"
    assert call_kwargs["properties"]["tags"]["multi_select"] == [
        {"name": "History"},
        {"name": "Landmark"},
    ]


async def test_execute_snapshot_run_sends_icon_and_cover_to_notion():
    """When pipelines set page_metadata, create_page receives icon and cover."""
    notion = MagicMock()
    notion.create_page.return_value = {"id": "page-1", "object": "page"}
    svc = JobExecutionService(notion_service=notion, dry_run=False)

    snapshot = {
        "job": {
            "stages": [
                {
                    "id": "stage_property_setting",
                    "sequence": 1,
                    "pipeline_run_mode": "sequential",
                    "pipelines": [
                        {
                            "id": "pipeline_cover",
                            "sequence": 1,
                            "steps": [
                                {
                                    "id": "step_cover_property_set",
                                    "step_template_id": "step_template_property_set",
                                    "sequence": 1,
                                    "input_bindings": {
                                        "value": {
                                            "static_value": {
                                                "type": "external",
                                                "external": {"url": "https://example.com/cover.jpg"},
                                            }
                                        }
                                    },
                                    "config": {
                                        "target_kind": "page_metadata",
                                        "target_field": "cover_image",
                                    },
                                }
                            ],
                        },
                        {
                            "id": "pipeline_icon",
                            "sequence": 2,
                            "steps": [
                                {
                                    "id": "step_icon_property_set",
                                    "step_template_id": "step_template_property_set",
                                    "sequence": 1,
                                    "input_bindings": {
                                        "value": {
                                            "static_value": {
                                                "type": "file_upload",
                                                "file_upload": {"id": "fu-123"},
                                            }
                                        }
                                    },
                                    "config": {
                                        "target_kind": "page_metadata",
                                        "target_field": "icon_image",
                                    },
                                }
                            ],
                        },
                    ],
                }
            ]
        },
        "target": {
            "display_name": "Places to Visit",
            "external_target_id": "ds-123",
        },
        "active_schema": {"properties": []},
    }

    await svc.execute_snapshot_run(
        snapshot=snapshot,
        run_id="run-1",
        job_id="job-1",
        trigger_payload={},
    )

    notion.create_page.assert_called_once()
    call_kwargs = notion.create_page.call_args.kwargs
    assert call_kwargs["cover"] == {
        "type": "external",
        "external": {"url": "https://example.com/cover.jpg"},
    }
    assert call_kwargs["icon"] == {"type": "file_upload", "file_upload": {"id": "fu-123"}}


async def test_execute_snapshot_run_logs_notion_create_failed_on_exception():
    """When create_page_with_token raises, job_execution_notion_create_failed is logged and error is re-raised."""
    get_token = AsyncMock(return_value="oauth-token")
    svc = JobExecutionService(
        notion_service=MagicMock(),
        dry_run=False,
        get_notion_token_fn=get_token,
    )

    snapshot = {
        "job": {
            "stages": [
                {
                    "id": "stage_property_setting",
                    "sequence": 1,
                    "pipeline_run_mode": "sequential",
                    "pipelines": [
                        {
                            "id": "pipeline_tags",
                            "sequence": 1,
                            "steps": [
                                {
                                    "id": "step_property_set_tags",
                                    "step_template_id": "step_template_property_set",
                                    "sequence": 1,
                                    "input_bindings": {"value": {"static_value": ["History"]}},
                                    "config": {
                                        "schema_property_id": "prop_tags",
                                    },
                                },
                            ],
                        },
                    ],
                },
            ]
        },
        "target": {"display_name": "Places", "external_target_id": "ds-fail-123"},
        "active_schema": {
            "properties": [
                {
                    "id": "prop_tags",
                    "external_property_id": "tags",
                    "property_type": "multi_select",
                    "options": [{"id": "o1", "name": "History"}],
                },
            ],
        },
    }

    with patch("app.services.notion_service.NotionService") as notion_cls:
        notion_cls.create_page_with_token.side_effect = ValueError("Could not find data_source")

        with patch("app.services.job_execution.job_execution_service.logger") as mock_logger:
            with pytest.raises(ValueError, match="Could not find data_source"):
                await svc.execute_snapshot_run(
                    snapshot=snapshot,
                    run_id="run-1",
                    job_id="job-1",
                    trigger_payload={"raw_input": "test"},
                    owner_user_id="user-1",
                )

    mock_logger.exception.assert_called_once()
    call_args = mock_logger.exception.call_args[0]
    assert "job_execution_notion_create_failed" in str(call_args)
    assert "run_id=run-1" in str(call_args) or "run-1" in str(call_args)
    assert "job_id=job-1" in str(call_args) or "job-1" in str(call_args)
    assert "data_source_id=ds-fail-123" in str(call_args) or "ds-fail-123" in str(call_args)
    assert "token_source=oauth" in str(call_args) or "oauth" in str(call_args)


async def test_execute_snapshot_run_logs_fallback_when_oauth_unavailable():
    """When owner_user_id is set but OAuth token is unavailable, logs fallback to global token."""
    notion = MagicMock()
    notion.create_page.return_value = {"id": "page-1", "object": "page"}
    get_token = AsyncMock(return_value=None)
    svc = JobExecutionService(
        notion_service=notion,
        dry_run=False,
        get_notion_token_fn=get_token,
    )

    snapshot = {
        "job": {
            "stages": [
                {
                    "id": "stage_property_setting",
                    "sequence": 1,
                    "pipeline_run_mode": "sequential",
                    "pipelines": [
                        {
                            "id": "pipeline_tags",
                            "sequence": 1,
                            "steps": [
                                {
                                    "id": "step_tags",
                                    "step_template_id": "step_template_property_set",
                                    "sequence": 1,
                                    "input_bindings": {"value": {"static_value": ["History"]}},
                                    "config": {
                                        "schema_property_id": "prop_tags",
                                    },
                                },
                            ],
                        },
                    ],
                },
            ]
        },
        "target": {"display_name": "Places", "external_target_id": "ds-123"},
        "active_schema": {
            "properties": [
                {
                    "id": "prop_tags",
                    "external_property_id": "tags",
                    "property_type": "multi_select",
                    "options": [{"id": "o1", "name": "History"}],
                },
            ],
        },
    }

    with patch("app.services.job_execution.job_execution_service.logger") as mock_logger:
        await svc.execute_snapshot_run(
            snapshot=snapshot,
            run_id="run-1",
            job_id="job-1",
            trigger_payload={},
            owner_user_id="user-oauth-missing",
        )

    mock_logger.warning.assert_called()
    fallback_calls = [c for c in mock_logger.warning.call_args_list if "notion_create_page_fallback_to_global_token" in str(c)]
    assert len(fallback_calls) == 1
    call_str = str(fallback_calls[0])
    assert "run_id=run-1" in call_str or "run-1" in call_str
    assert "user-oauth-missing" in call_str
    assert "ds-123" in call_str
    assert "oauth_token_unavailable" in call_str
    notion.create_page.assert_called_once()
