"""Unit tests for Google Maps URL pipeline and related components."""

from unittest.mock import MagicMock

import pytest

from app.custom_pipelines.google_maps_url import GoogleMapsUrlPipeline
from app.models.schema import PropertySchema
from app.pipeline_lib.context import ContextKeys as CtxKeys, PipelineRunContext
from app.pipeline_lib.orchestration import _run_pipeline
from app.pipeline_lib.stage_pipelines.google_places import GooglePlacesToCacheStep
from app.pipeline_lib.steps.google_places import ExtractGoogleMapsUri
from app.services.google_places_service import GooglePlacesService


def test_google_places_service_normalize_includes_google_maps_uri():
    """_normalize_place includes googleMapsUri in normalized output."""
    svc = GooglePlacesService(api_key="test-key")
    place_raw = {
        "id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
        "displayName": {"text": "Stone Arch Bridge"},
        "formattedAddress": "1 Main St, Minneapolis",
        "googleMapsUri": "https://maps.google.com/?cid=3545450935484072529",
        "primaryType": "tourist_attraction",
        "types": ["tourist_attraction", "point_of_interest"],
    }
    normalized = svc._normalize_place(place_raw)
    assert normalized.get("googleMapsUri") == "https://maps.google.com/?cid=3545450935484072529"
    assert normalized.get("id") == "ChIJN1t_tDeuEmsRUsoyG83frY4"
    assert normalized.get("primaryType") == "tourist_attraction"
    assert normalized.get("types") == ["tourist_attraction", "point_of_interest"]


def test_google_places_service_normalize_handles_missing_google_maps_uri():
    """_normalize_place returns empty string when googleMapsUri is absent."""
    svc = GooglePlacesService(api_key="test-key")
    place_raw = {"id": "ChIJabc123", "displayName": {"text": "Test"}}
    normalized = svc._normalize_place(place_raw)
    assert normalized.get("googleMapsUri", "") == ""
    assert normalized.get("primaryType") is None
    assert normalized.get("types") == []


def test_google_places_service_normalize_includes_summary_fields():
    """_normalize_place extracts generativeSummary and editorialSummary from API response."""
    svc = GooglePlacesService(api_key="test-key")
    place_raw = {
        "id": "ChIJ123",
        "displayName": {"text": "Stone Arch Bridge"},
        "generativeSummary": {
            "overview": {"text": "Historic bridge spanning the Mississippi.", "languageCode": "en-US"},
        },
        "editorialSummary": {"text": "Landmark pedestrian bridge.", "languageCode": "en"},
    }
    normalized = svc._normalize_place(place_raw)
    assert normalized.get("generativeSummary") == "Historic bridge spanning the Mississippi."
    assert normalized.get("editorialSummary") == "Landmark pedestrian bridge."


def test_google_places_service_normalize_includes_photos():
    """_normalize_place extracts photos array with name, widthPx, heightPx."""
    svc = GooglePlacesService(api_key="test-key")
    place_raw = {
        "id": "ChIJ123",
        "displayName": {"text": "Stone Arch Bridge"},
        "photos": [
            {
                "name": "places/ChIJ123/photos/ABC123",
                "widthPx": 4000,
                "heightPx": 3000,
            },
        ],
    }
    normalized = svc._normalize_place(place_raw)
    assert "photos" in normalized
    assert len(normalized["photos"]) == 1
    assert normalized["photos"][0]["name"] == "places/ChIJ123/photos/ABC123"
    assert normalized["photos"][0]["widthPx"] == 4000
    assert normalized["photos"][0]["heightPx"] == 3000


def test_google_places_service_search_places_returns_list_by_default():
    """search_places returns list of normalized places when return_raw_response=False."""
    svc = GooglePlacesService(api_key="test-key")
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "places": [
            {"id": "ChIJ123", "displayName": {"text": "Stone Arch Bridge"}, "formattedAddress": "1 Main St"},
        ],
    }
    mock_response.raise_for_status = MagicMock()
    svc._client.post = MagicMock(return_value=mock_response)

    result = svc.search_places("stone arch bridge")

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["displayName"] == "Stone Arch Bridge"
    assert result[0]["id"] == "ChIJ123"


def test_google_places_service_search_places_returns_tuple_when_raw_requested():
    """search_places returns (normalized_list, raw_response) when return_raw_response=True."""
    svc = GooglePlacesService(api_key="test-key")
    raw_api_response = {
        "places": [
            {"id": "ChIJ123", "displayName": {"text": "Stone Arch Bridge"}, "formattedAddress": "1 Main St"},
        ],
    }
    mock_response = MagicMock()
    mock_response.json.return_value = raw_api_response
    mock_response.raise_for_status = MagicMock()
    svc._client.post = MagicMock(return_value=mock_response)

    result = svc.search_places("stone arch bridge", return_raw_response=True)

    assert isinstance(result, tuple)
    normalized, raw = result
    assert len(normalized) == 1
    assert normalized[0]["displayName"] == "Stone Arch Bridge"
    assert raw == raw_api_response


def test_google_places_service_get_place_details_returns_dict_by_default():
    """get_place_details returns normalized dict when return_raw_response=False."""
    svc = GooglePlacesService(api_key="test-key")
    raw_place = {"id": "ChIJ123", "displayName": {"text": "Stone Arch Bridge"}}
    mock_response = MagicMock()
    mock_response.json.return_value = raw_place
    mock_response.raise_for_status = MagicMock()
    svc._client.get = MagicMock(return_value=mock_response)

    result = svc.get_place_details("ChIJ123")

    assert isinstance(result, dict)
    assert result["displayName"] == "Stone Arch Bridge"
    assert result["id"] == "ChIJ123"


def test_google_places_service_get_place_details_returns_tuple_when_raw_requested():
    """get_place_details returns (normalized, raw) when return_raw_response=True."""
    svc = GooglePlacesService(api_key="test-key")
    raw_place = {"id": "ChIJ123", "displayName": {"text": "Stone Arch Bridge"}}
    mock_response = MagicMock()
    mock_response.json.return_value = raw_place
    mock_response.raise_for_status = MagicMock()
    svc._client.get = MagicMock(return_value=mock_response)

    result = svc.get_place_details("ChIJ123", return_raw_response=True)

    assert isinstance(result, tuple)
    normalized, raw = result
    assert normalized["displayName"] == "Stone Arch Bridge"
    assert raw == raw_place


def test_google_places_to_cache_step_sets_google_place_and_logs_raw_response():
    """GooglePlacesToCacheStep sets GOOGLE_PLACE and emits DEBUG log with raw response."""
    mock_google = MagicMock()
    normalized_place = {"id": "ChIJ123", "displayName": "Stone Arch Bridge", "formattedAddress": "1 Main St"}
    raw_search_response = {"places": [{"id": "ChIJ123", "displayName": {"text": "Stone Arch Bridge"}}]}
    mock_google.search_places.return_value = ([normalized_place], raw_search_response)

    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.RAW_QUERY: "stone arch bridge",
        CtxKeys.REWRITTEN_QUERY: "stone arch bridge minneapolis",
    })
    ctx.set("_global_pipeline_id", "gp1")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")
    ctx.set("_google_places_service", mock_google)

    step = GooglePlacesToCacheStep(fetch_details_if_needed=False)
    result = step.execute(ctx, None)

    assert result == normalized_place
    assert ctx.get(CtxKeys.GOOGLE_PLACE) == normalized_place
    mock_google.search_places.assert_called_once_with("stone arch bridge minneapolis", return_raw_response=True)


def test_google_places_service_get_photo_url_returns_photo_uri():
    """get_photo_url returns photoUri from Places Photo Media API response."""
    svc = GooglePlacesService(api_key="test-key")
    mock_response = MagicMock()
    mock_response.json.return_value = {"photoUri": "https://lh3.googleusercontent.com/photo.jpg"}
    mock_response.raise_for_status = MagicMock()
    svc._client.get = MagicMock(return_value=mock_response)

    url = svc.get_photo_url("places/ChIJ123/photos/ABC123")

    assert url == "https://lh3.googleusercontent.com/photo.jpg"
    svc._client.get.assert_called_once()
    call_args = svc._client.get.call_args
    assert "places/ChIJ123/photos/ABC123/media" in call_args[0][0]
    assert call_args[1]["params"]["skipHttpRedirect"] == "true"


def test_google_places_service_get_photo_url_returns_none_on_failure():
    """get_photo_url returns None when API call fails."""
    from unittest.mock import MagicMock

    svc = GooglePlacesService(api_key="test-key")
    svc._client.get = MagicMock(side_effect=Exception("Network error"))

    url = svc.get_photo_url("places/ChIJ123/photos/ABC123")

    assert url is None


def test_google_places_service_get_photo_bytes_returns_image():
    """get_photo_bytes returns image bytes when API redirects to image."""
    from unittest.mock import MagicMock

    svc = GooglePlacesService(api_key="test-key")
    mock_response = MagicMock()
    mock_response.content = b"\xff\xd8\xff fake jpeg"
    mock_response.headers = {"content-type": "image/jpeg"}
    mock_response.raise_for_status = MagicMock()
    svc._client.get = MagicMock(return_value=mock_response)

    data = svc.get_photo_bytes("places/ChIJ123/photos/ABC123")

    assert data == b"\xff\xd8\xff fake jpeg"
    svc._client.get.assert_called_once()
    call_kwargs = svc._client.get.call_args[1]
    assert call_kwargs.get("follow_redirects") is True


def test_google_places_service_get_photo_bytes_returns_none_on_non_image():
    """get_photo_bytes returns None when response is not an image."""
    from unittest.mock import MagicMock

    svc = GooglePlacesService(api_key="test-key")
    mock_response = MagicMock()
    mock_response.content = b"not an image"
    mock_response.headers = {"content-type": "text/html"}
    mock_response.raise_for_status = MagicMock()
    svc._client.get = MagicMock(return_value=mock_response)

    data = svc.get_photo_bytes("places/ChIJ123/photos/ABC123")

    assert data is None


def test_extract_google_maps_uri_returns_uri_when_present():
    """ExtractGoogleMapsUri returns googleMapsUri when available."""
    step = ExtractGoogleMapsUri()
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {
            "id": "ChIJ123",
            "googleMapsUri": "https://maps.google.com/?cid=123",
        },
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    result = step.execute(ctx, None)
    assert result == "https://maps.google.com/?cid=123"


def test_extract_google_maps_uri_fallback_to_place_id_when_uri_empty():
    """ExtractGoogleMapsUri falls back to place_id URL when googleMapsUri is empty."""
    step = ExtractGoogleMapsUri()
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {
            "id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
            "googleMapsUri": "",
        },
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    result = step.execute(ctx, None)
    assert result == "https://www.google.com/maps/place/?q=place_id:ChIJN1t_tDeuEmsRUsoyG83frY4"


def test_extract_google_maps_uri_returns_none_when_no_place():
    """ExtractGoogleMapsUri returns None when google_place is missing."""
    step = ExtractGoogleMapsUri()
    ctx = PipelineRunContext(run_id="r1", initial={})
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    result = step.execute(ctx, None)
    assert result is None


def test_extract_google_maps_uri_returns_none_when_no_place_id_or_uri():
    """ExtractGoogleMapsUri returns None when both googleMapsUri and id are empty."""
    step = ExtractGoogleMapsUri()
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {"id": "", "googleMapsUri": ""},
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    result = step.execute(ctx, None)
    assert result is None


def test_google_maps_url_pipeline_sets_property():
    """GoogleMapsUrlPipeline extracts URL and sets property in context."""
    schema = PropertySchema(name="Google Maps", type="url", options=None)
    pipeline = GoogleMapsUrlPipeline("Google Maps", schema)
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {
            "id": "ChIJ123",
            "googleMapsUri": "https://maps.google.com/?cid=456",
        },
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Google Maps" in props
    assert props["Google Maps"] == {"url": "https://maps.google.com/?cid=456"}


def test_google_maps_url_pipeline_fallback_place_id():
    """GoogleMapsUrlPipeline uses place_id fallback when googleMapsUri absent."""
    schema = PropertySchema(name="Google Maps", type="url", options=None)
    pipeline = GoogleMapsUrlPipeline("Google Maps", schema)
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {
            "id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
            "googleMapsUri": "",
        },
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Google Maps" in props
    expected = "https://www.google.com/maps/place/?q=place_id:ChIJN1t_tDeuEmsRUsoyG83frY4"
    assert props["Google Maps"] == {"url": expected}


def test_google_maps_url_pipeline_records_property_source():
    """Pipeline run records which pipeline resolved each property in get_property_sources."""
    schema = PropertySchema(name="Google Maps", type="url", options=None)
    pipeline = GoogleMapsUrlPipeline("Google Maps", schema)
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {
            "id": "ChIJ123",
            "googleMapsUri": "https://maps.google.com/?cid=456",
        },
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    sources = ctx.get_property_sources()
    assert "Google Maps" in sources
    assert sources["Google Maps"] == "google_maps_Google Maps"
