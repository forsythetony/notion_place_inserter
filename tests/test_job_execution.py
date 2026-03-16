"""Unit tests for snapshot-driven job execution (p3_pr06)."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.job_execution.binding_resolver import resolve_binding, resolve_input_bindings
from app.services.job_execution.job_execution_service import JobExecutionService
from app.services.job_execution.runtime_types import ExecutionContext
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


def test_resolve_signal_ref_trigger_payload():
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


def test_resolve_signal_ref_step_output():
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


def test_resolve_signal_ref_step_output_nested_path():
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


def test_resolve_cache_key():
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


def test_resolve_static_value():
    """static_value returns literal."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    result = resolve_binding({"static_value": "literal"}, ctx, {})
    assert result == "literal"


def test_resolve_target_schema_ref_options():
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
                "data_target_id": "t1",
                "schema_property_id": "prop_tags",
                "field": "options",
            },
        },
        ctx,
        snapshot,
    )
    assert result == [{"id": "opt1", "name": "History"}, {"id": "opt2", "name": "Landmark"}]


def test_resolve_input_bindings_multiple():
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


def test_cache_set_handler_stores_in_run_cache():
    """CacheSetHandler stores value in run_cache."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = CacheSetHandler()
    handler.execute(
        step_id="step_cache",
        config={"cache_key": "my_key"},
        input_bindings={"value": {"signal_ref": "trigger.payload.raw_input"}},
        resolved_inputs={"value": "stored_value"},
        ctx=ctx,
        snapshot={},
    )
    assert ctx.run_cache.get("my_key") == "stored_value"


def test_cache_get_handler_returns_cached_value():
    """CacheGetHandler returns value from run_cache."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx.run_cache["my_key"] = "cached"
    handler = CacheGetHandler()
    result = handler.execute(
        step_id="step_get",
        config={"cache_key": "my_key"},
        input_bindings={},
        resolved_inputs={},
        ctx=ctx,
        snapshot={},
    )
    assert result == {"value": "cached"}


def test_property_set_handler_stores_in_properties():
    """PropertySetHandler stores value in ctx.properties."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = PropertySetHandler()
    handler.execute(
        step_id="step_prop",
        config={"schema_property_id": "prop_tags"},
        input_bindings={"value": {}},
        resolved_inputs={"value": ["History", "Landmark"]},
        ctx=ctx,
        snapshot={},
    )
    assert ctx.properties.get("prop_tags") == ["History", "Landmark"]


def test_property_set_handler_stores_in_page_metadata_cover():
    """PropertySetHandler with target_kind=page_metadata sets ctx.cover."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = PropertySetHandler()
    payload = {"type": "external", "external": {"url": "https://example.com/cover.jpg"}}
    handler.execute(
        step_id="step_cover",
        config={"data_target_id": "t1", "target_kind": "page_metadata", "target_field": "cover_image"},
        input_bindings={"value": {}},
        resolved_inputs={"value": payload},
        ctx=ctx,
        snapshot={},
    )
    assert ctx.cover == payload


def test_property_set_handler_stores_in_page_metadata_icon():
    """PropertySetHandler with target_kind=page_metadata sets ctx.icon."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = PropertySetHandler()
    payload = {"type": "file_upload", "file_upload": {"id": "fu-123"}}
    handler.execute(
        step_id="step_icon",
        config={"data_target_id": "t1", "target_kind": "page_metadata", "target_field": "icon_image"},
        input_bindings={"value": {}},
        resolved_inputs={"value": payload},
        ctx=ctx,
        snapshot={},
    )
    assert ctx.icon == payload


def test_property_set_handler_page_metadata_converts_url_string():
    """PropertySetHandler converts URL string to external payload for page_metadata."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = PropertySetHandler()
    handler.execute(
        step_id="step_cover",
        config={"data_target_id": "t1", "target_kind": "page_metadata", "target_field": "cover_image"},
        input_bindings={"value": {}},
        resolved_inputs={"value": "https://example.com/img.png"},
        ctx=ctx,
        snapshot={},
    )
    assert ctx.cover == {"type": "external", "external": {"url": "https://example.com/img.png"}}


def test_data_transform_handler_extract_key():
    """DataTransformHandler extracts value at source_path."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = DataTransformHandler()
    value = {"photos": [{"name": "places/abc/photos/xyz"}, {"name": "places/def/photos/uvw"}]}
    result = handler.execute(
        step_id="step_transform",
        config={"operation": "extract_key", "source_path": "photos[0].name"},
        input_bindings={"value": {}},
        resolved_inputs={"value": value},
        ctx=ctx,
        snapshot={},
    )
    assert result["transformed_value"] == "places/abc/photos/xyz"


def test_data_transform_handler_returns_fallback_when_path_missing():
    """DataTransformHandler returns fallback_value when path missing."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = DataTransformHandler()
    result = handler.execute(
        step_id="step_transform",
        config={
            "operation": "extract_key",
            "source_path": "photos[0].url",
            "fallback_value": "default.jpg",
        },
        input_bindings={"value": {}},
        resolved_inputs={"value": {"photos": [{"name": "x"}]}},
        ctx=ctx,
        snapshot={},
    )
    assert result["transformed_value"] == "default.jpg"


def test_templater_handler_renders_template():
    """TemplaterHandler replaces {{key}} placeholders with values."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = TemplaterHandler()
    result = handler.execute(
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
        snapshot={},
    )
    assert result["rendered_value"] == "44.9778, -93.265"  # float str() drops trailing zero


def test_templater_handler_signal_ref_resolution():
    """TemplaterHandler resolves signal_ref in values (e.g. from step output or cache_get)."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx.set_step_output(
        "step_cache_get_place",
        "value",
        {"latitude": 19.43, "longitude": -99.16},
    )
    handler = TemplaterHandler()
    result = handler.execute(
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
        snapshot={},
    )
    assert result["rendered_value"] == "19.43, -99.16"


def test_templater_handler_cache_key_ref_resolution():
    """TemplaterHandler resolves cache_key in values (flat cached value)."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx.run_cache["lat"] = 44.9778
    ctx.run_cache["lng"] = -93.2650
    handler = TemplaterHandler()
    result = handler.execute(
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
        snapshot={},
    )
    assert result["rendered_value"] == "44.9778, -93.265"  # float str() drops trailing zero


def test_templater_handler_missing_key_renders_empty():
    """TemplaterHandler renders empty string for missing placeholder keys."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = TemplaterHandler()
    result = handler.execute(
        step_id="step_templater",
        config={
            "template": "{{a}}-{{b}}-{{c}}",
            "values": {"a": {"static_value": "x"}, "c": {"static_value": "z"}},
        },
        input_bindings={},
        resolved_inputs={},
        ctx=ctx,
        snapshot={},
    )
    assert result["rendered_value"] == "x--z"


def test_templater_handler_non_string_values_stringify():
    """TemplaterHandler stringifies non-string values (int, float, dict)."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = TemplaterHandler()
    result = handler.execute(
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
        snapshot={},
    )
    assert result["rendered_value"] == "42 3.14"


def test_step_runtime_registry_get_returns_templater_handler():
    """StepRuntimeRegistry returns TemplaterHandler for step_template_templater."""
    reg = StepRuntimeRegistry()
    reg.register("step_template_templater", TemplaterHandler)
    handler = reg.get("step_template_templater")
    assert handler is not None
    assert isinstance(handler, TemplaterHandler)


def test_search_icons_handler_returns_url_when_freepik_available():
    """SearchIconsHandler returns image_url from Freepik when service available."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx._services["freepik"] = MagicMock()
    ctx._services["freepik"].get_first_icon_url.return_value = "https://cdn.freepik.com/icon.png"
    handler = SearchIconsHandler()
    result = handler.execute(
        step_id="step_search",
        config={},
        input_bindings={"query": {}},
        resolved_inputs={"query": "coffee shop"},
        ctx=ctx,
        snapshot={},
    )
    assert result["image_url"] == "https://cdn.freepik.com/icon.png"


def test_search_icons_handler_returns_none_when_no_freepik():
    """SearchIconsHandler returns None when Freepik service not configured."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = SearchIconsHandler()
    result = handler.execute(
        step_id="step_search",
        config={},
        input_bindings={"query": {}},
        resolved_inputs={"query": "bridge"},
        ctx=ctx,
        snapshot={},
    )
    assert result["image_url"] is None


def test_upload_image_to_notion_handler_dry_run_passthrough_external_url():
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
        result = handler.execute(
            step_id="step_upload",
            config={},
            input_bindings={"value": {}},
            resolved_inputs={"value": "https://example.com/image.jpg"},
            ctx=ctx,
            snapshot={},
        )
    assert result["notion_image_url"] == {
        "type": "external",
        "external": {"url": "https://example.com/image.jpg"},
    }


def test_upload_image_to_notion_handler_dry_run_never_uploads_when_bytes_available():
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
        result = handler.execute(
            step_id="step_upload",
            config={},
            input_bindings={"value": {}},
            resolved_inputs={"value": "https://example.com/image.jpg"},
            ctx=ctx,
            snapshot={},
        )
    assert result["notion_image_url"] == {
        "type": "external",
        "external": {"url": "https://example.com/image.jpg"},
    }
    fetch_mock.assert_not_called()
    notion.upload_cover_from_bytes.assert_not_called()


def test_upload_image_to_notion_handler_dry_run_google_photo_uses_external_url_only():
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

    result = handler.execute(
        step_id="step_upload",
        config={},
        input_bindings={"value": {}},
        resolved_inputs={"value": "places/abc/photos/def"},
        ctx=ctx,
        snapshot={},
    )

    assert result["notion_image_url"] == {
        "type": "external",
        "external": {"url": "https://example.com/google-photo.jpg"},
    }
    google.get_photo_url.assert_called_once_with("places/abc/photos/def")
    google.get_photo_bytes.assert_not_called()
    notion.upload_cover_from_bytes.assert_not_called()


def test_upload_image_to_notion_handler_uses_oauth_token_for_upload_when_available():
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
        result = handler.execute(
            step_id="step_upload",
            config={},
            input_bindings={"value": {}},
            resolved_inputs={"value": "https://example.com/image.jpg"},
            ctx=ctx,
            snapshot={},
        )

    assert result["notion_image_url"] == {"type": "file_upload", "file_upload": {"id": "fu-1"}}
    notion.upload_cover_from_bytes.assert_called_once_with(
        b"fake-image-bytes",
        filename="image.jpg",
        content_type="image/jpeg",
        access_token="oauth-token-abc",
    )


def test_optimize_input_claude_handler_returns_optimized_query():
    """OptimizeInputClaudeHandler returns optimized_query (or passthrough when no Claude)."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    handler = OptimizeInputClaudeHandler()
    result = handler.execute(
        step_id="step_opt",
        config={"prompt": "Rewrite"},
        input_bindings={"query": {}},
        resolved_inputs={"query": "coffee shop"},
        ctx=ctx,
        snapshot={},
    )
    assert "optimized_query" in result
    assert result["optimized_query"] == "coffee shop"  # no Claude, passthrough


def test_ai_prompt_handler_returns_value_when_claude_available():
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
    result = handler.execute(
        step_id="step_ai_prompt",
        config={"prompt": "Rewrite into a travel note."},
        input_bindings={"value": {}},
        resolved_inputs={"value": {"displayName": "Joe's Coffee", "formattedAddress": "123 Main St"}},
        ctx=ctx,
        snapshot={},
    )
    assert result["value"] == "A charming café in downtown."
    claude.prompt_completion.assert_called_once_with(
        prompt="Rewrite into a travel note.",
        value={"displayName": "Joe's Coffee", "formattedAddress": "123 Main St"},
        max_tokens=1024,
    )


def test_ai_prompt_handler_returns_empty_when_no_claude():
    """AiPromptHandler returns empty string when Claude service not configured."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    handler = AiPromptHandler()
    result = handler.execute(
        step_id="step_ai_prompt",
        config={"prompt": "Rewrite."},
        input_bindings={"value": {}},
        resolved_inputs={"value": "input text"},
        ctx=ctx,
        snapshot={},
    )
    assert result["value"] == ""


def test_step_runtime_registry_get_returns_handler():
    """StepRuntimeRegistry returns handler for registered step_template_id."""
    from app.services.job_execution.handlers import CacheSetHandler

    reg = StepRuntimeRegistry()
    reg.register("step_template_cache_set", CacheSetHandler)
    handler = reg.get("step_template_cache_set")
    assert handler is not None
    assert isinstance(handler, CacheSetHandler)


def test_step_runtime_registry_get_unknown_returns_none():
    """StepRuntimeRegistry returns None for unknown step_template_id."""
    reg = StepRuntimeRegistry()
    assert reg.get("step_template_unknown") is None


def test_build_notion_properties_payload_multi_select():
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


def test_build_notion_properties_payload_relation():
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


def test_ai_select_relation_handler_no_match_returns_empty():
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
    result = handler.execute(
        step_id="step_ai_select",
        config={"related_db": "target_locations", "key_lookup": "title"},
        input_bindings={"source_value": {}},
        resolved_inputs={"source_value": {"displayName": "Stone Arch Bridge", "formattedAddress": "Minneapolis, MN"}},
        ctx=ctx,
        snapshot={"targets": {"target_locations": {"external_target_id": "ds-locations"}}},
    )
    assert result["selected_page_pointer"] is None or result["selected_relation"] == []
    assert "selected_relation" in result


def test_ai_select_relation_handler_selects_match_when_claude_returns_id():
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
    result = handler.execute(
        step_id="step_ai_select",
        config={"related_db": "target_locations", "key_lookup": "title"},
        input_bindings={"source_value": {}},
        resolved_inputs={"source_value": {"displayName": "Stone Arch Bridge", "formattedAddress": "Minneapolis, MN"}},
        ctx=ctx,
        snapshot={"targets": {"target_locations": {"external_target_id": "ds-locations"}}},
    )
    assert result["selected_relation"] == [{"id": "loc-1"}]
    assert result["selected_page_pointer"] == {"id": "loc-1"}


def test_ai_select_relation_prefers_get_data_source_id_over_external_target_id():
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
    result = handler.execute(
        step_id="step_ai_select",
        config={"related_db": "target_locations", "key_lookup": "title"},
        input_bindings={"source_value": {}},
        resolved_inputs={"source_value": "1401 West River Rd N, Minneapolis, MN 55411, USA"},
        ctx=ctx,
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


def test_ai_select_relation_returns_empty_on_query_failure():
    """AiSelectRelationHandler returns empty relation when Notion query fails."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    notion = MagicMock()
    notion.get_data_source_id.return_value = "ds-123"
    notion.client = MagicMock()
    notion.client.data_sources.query.side_effect = Exception("Could not find database with ID")
    ctx._services["notion"] = notion
    handler = AiSelectRelationHandler()
    result = handler.execute(
        step_id="step_ai_select",
        config={"related_db": "target_locations", "key_lookup": "title"},
        input_bindings={"source_value": {}},
        resolved_inputs={"source_value": "Minneapolis, MN"},
        ctx=ctx,
        snapshot={"targets": {"target_locations": {"display_name": "Locations"}}},
    )
    assert result["selected_relation"] == []
    assert result["selected_page_pointer"] is None


def test_ai_select_relation_accepts_address_only_input():
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
    result = handler.execute(
        step_id="step_ai_select",
        config={"related_db": "target_locations", "key_lookup": "title"},
        input_bindings={"source_value": {}},
        resolved_inputs={"source_value": "1401 West River Rd N, Minneapolis, MN 55411, USA"},
        ctx=ctx,
        snapshot={"targets": {"target_locations": {"display_name": "Locations"}}},
    )
    assert result["selected_relation"] == [{"id": "loc-twin"}]
    claude.choose_best_relation_from_candidates.assert_called_once()
    call_kwargs = claude.choose_best_relation_from_candidates.call_args.kwargs
    assert call_kwargs["source_context"] == {"value": "1401 West River Rd N, Minneapolis, MN 55411, USA"}


def test_ai_select_relation_uses_valid_filter_properties_from_data_source_schema():
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

    result = handler.execute(
        step_id="step_ai_select",
        config={"related_db": "target_locations", "key_lookup": "title"},
        input_bindings={"source_value": {}},
        resolved_inputs={"source_value": "Minneapolis, MN"},
        ctx=ctx,
        snapshot={"targets": {"target_locations": {"display_name": "Locations"}}},
    )

    assert result["selected_relation"] == [{"id": "loc-mpls"}]
    call_kwargs = notion.client.data_sources.query.call_args.kwargs
    assert call_kwargs["data_source_id"] == "ds-123"
    assert call_kwargs["filter_properties"] == ["title", "Name"]


def test_ai_select_relation_retries_without_filter_properties_on_validation_error():
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

    result = handler.execute(
        step_id="step_ai_select",
        config={"related_db": "target_locations", "key_lookup": "title"},
        input_bindings={"source_value": {}},
        resolved_inputs={"source_value": "Minneapolis, MN"},
        ctx=ctx,
        snapshot={"targets": {"target_locations": {"display_name": "Locations"}}},
    )

    assert result["selected_relation"] == [{"id": "loc-twin"}]
    assert notion.client.data_sources.query.call_count == 2
    first_kwargs = notion.client.data_sources.query.call_args_list[0].kwargs
    second_kwargs = notion.client.data_sources.query.call_args_list[1].kwargs
    assert first_kwargs["filter_properties"] == ["title", "Name"]
    assert "filter_properties" not in second_kwargs


def test_execute_snapshot_run_synthesizes_schema_when_missing():
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
                                        "data_target_id": "target_places_to_visit",
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

    result = svc.execute_snapshot_run(
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


def test_execute_snapshot_run_dry_run_delegates_to_notion_service():
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
                                        "data_target_id": "target_places_to_visit",
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

    result = svc.execute_snapshot_run(
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


def test_execute_snapshot_run_sends_icon_and_cover_to_notion():
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
                                        "data_target_id": "target_places_to_visit",
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
                                        "data_target_id": "target_places_to_visit",
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

    svc.execute_snapshot_run(
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
