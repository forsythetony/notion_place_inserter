"""Unit tests for geolocation pipelines: latitude, longitude, coordinates."""

import pytest

from app.custom_pipelines.coordinates import CoordinatesPipeline
from app.custom_pipelines.latitude import LatitudePipeline
from app.custom_pipelines.longitude import LongitudePipeline
from app.models.schema import PropertySchema
from app.pipeline_lib.context import ContextKeys as CtxKeys, PipelineRunContext
from app.pipeline_lib.orchestration import _run_pipeline
from app.pipeline_lib.steps.google_places import (
    ExtractCoordinates,
    ExtractLatitude,
    ExtractLongitude,
)
from app.services.google_places_service import GooglePlacesService


def test_google_places_service_normalize_includes_latitude_longitude():
    """_normalize_place includes latitude and longitude when location is present."""
    svc = GooglePlacesService(api_key="test-key")
    place_raw = {
        "id": "ChIJ123",
        "displayName": {"text": "Stone Arch Bridge"},
        "location": {"latitude": 44.9816, "longitude": -93.2577},
    }
    normalized = svc._normalize_place(place_raw)
    assert normalized.get("latitude") == 44.9816
    assert normalized.get("longitude") == -93.2577


def test_google_places_service_normalize_handles_missing_location():
    """_normalize_place sets latitude/longitude to None when location is absent."""
    svc = GooglePlacesService(api_key="test-key")
    place_raw = {"id": "ChIJabc123", "displayName": {"text": "Test"}}
    normalized = svc._normalize_place(place_raw)
    assert normalized.get("latitude") is None
    assert normalized.get("longitude") is None


def test_google_places_service_normalize_extracts_neighborhood_from_address_components():
    """_normalize_place extracts neighborhood from addressComponents when present."""
    svc = GooglePlacesService(api_key="test-key")
    place_raw = {
        "id": "ChIJ123",
        "displayName": {"text": "Loring Park"},
        "formattedAddress": "1382 Willow St, Minneapolis, MN",
        "addressComponents": [
            {"longText": "Loring Park", "shortText": "Loring Park", "types": ["neighborhood"]},
            {"longText": "Minneapolis", "shortText": "Minneapolis", "types": ["locality"]},
        ],
    }
    normalized = svc._normalize_place(place_raw)
    assert normalized.get("neighborhood") == "Loring Park"


def test_google_places_service_normalize_uses_locality_when_no_neighborhood():
    """_normalize_place falls back to locality when neighborhood/sublocality absent."""
    svc = GooglePlacesService(api_key="test-key")
    place_raw = {
        "id": "ChIJ123",
        "displayName": {"text": "Downtown Cafe"},
        "addressComponents": [
            {"longText": "Minneapolis", "shortText": "Minneapolis", "types": ["locality"]},
        ],
    }
    normalized = svc._normalize_place(place_raw)
    assert normalized.get("neighborhood") == "Minneapolis"


def test_google_places_service_normalize_neighborhood_none_when_no_components():
    """_normalize_place sets neighborhood to None when addressComponents empty or absent."""
    svc = GooglePlacesService(api_key="test-key")
    place_raw = {"id": "ChIJ123", "displayName": {"text": "Remote Landmark"}}
    normalized = svc._normalize_place(place_raw)
    assert normalized.get("neighborhood") is None


def test_google_places_service_normalize_includes_neighborhood_debug_signals():
    """_normalize_place includes google_neighborhood_signals for debug logging."""
    svc = GooglePlacesService(api_key="test-key")
    place_raw = {
        "id": "ChIJ123",
        "displayName": {"text": "Loring Park"},
        "addressComponents": [
            {"longText": "Loring Park", "shortText": "Loring Park", "types": ["neighborhood"]},
            {"longText": "Minneapolis", "shortText": "Minneapolis", "types": ["locality"]},
        ],
    }
    normalized = svc._normalize_place(place_raw)
    signals = normalized.get("google_neighborhood_signals", [])
    assert len(signals) >= 1
    assert any(s.get("text") == "Loring Park" and "neighborhood" in (s.get("types") or []) for s in signals)


def test_google_places_service_normalize_extracts_sublocality_level_1_as_neighborhood():
    """_normalize_place extracts neighborhood from sublocality_level_1 when present."""
    svc = GooglePlacesService(api_key="test-key")
    place_raw = {
        "id": "ChIJ123",
        "displayName": {"text": "Blanco Colima"},
        "formattedAddress": "Av. Álvaro Obregón, Roma Norte, CDMX",
        "addressComponents": [
            {
                "longText": "Roma Norte",
                "shortText": "Roma Nte.",
                "types": ["sublocality_level_1", "sublocality", "political"],
                "languageCode": "es",
            },
            {"longText": "Ciudad de México", "shortText": "CDMX", "types": ["locality"]},
        ],
    }
    normalized = svc._normalize_place(place_raw)
    assert normalized.get("neighborhood") == "Roma Norte"
    assert normalized.get("neighborhood_signal_type") == "sublocality_level_1"


def test_google_places_service_normalize_prefers_sublocality_level_1_over_locality():
    """_normalize_place prefers sublocality_level_1 over locality when both present."""
    svc = GooglePlacesService(api_key="test-key")
    place_raw = {
        "id": "ChIJ123",
        "displayName": {"text": "Test Place"},
        "addressComponents": [
            {"longText": "Ciudad de México", "shortText": "CDMX", "types": ["locality"]},
            {
                "longText": "Roma Norte",
                "shortText": "Roma Nte.",
                "types": ["sublocality_level_1", "sublocality", "political"],
            },
        ],
    }
    normalized = svc._normalize_place(place_raw)
    assert normalized.get("neighborhood") == "Roma Norte"
    assert normalized.get("neighborhood_signal_type") == "sublocality_level_1"


def test_google_places_service_normalize_includes_sublocality_level_1_in_debug_signals():
    """_normalize_place includes sublocality_level_1 in google_neighborhood_signals."""
    svc = GooglePlacesService(api_key="test-key")
    place_raw = {
        "id": "ChIJ123",
        "displayName": {"text": "Blanco Colima"},
        "addressComponents": [
            {
                "longText": "Roma Norte",
                "shortText": "Roma Nte.",
                "types": ["sublocality_level_1", "sublocality", "political"],
            },
            {"longText": "Ciudad de México", "shortText": "CDMX", "types": ["locality"]},
        ],
    }
    normalized = svc._normalize_place(place_raw)
    signals = normalized.get("google_neighborhood_signals", [])
    assert any(
        s.get("text") == "Roma Norte" and "sublocality_level_1" in (s.get("types") or [])
        for s in signals
    )


def test_extract_latitude_returns_value_when_present():
    """ExtractLatitude returns latitude when available."""
    step = ExtractLatitude()
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {"latitude": 44.9816, "longitude": -93.2577},
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    result = step.execute(ctx, None)
    assert result == 44.9816


def test_extract_latitude_returns_none_when_missing():
    """ExtractLatitude returns None when latitude is absent."""
    step = ExtractLatitude()
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {"longitude": -93.2577},
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    result = step.execute(ctx, None)
    assert result is None


def test_extract_latitude_returns_none_when_no_place():
    """ExtractLatitude returns None when google_place is missing."""
    step = ExtractLatitude()
    ctx = PipelineRunContext(run_id="r1", initial={})
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    result = step.execute(ctx, None)
    assert result is None


def test_extract_longitude_returns_value_when_present():
    """ExtractLongitude returns longitude when available."""
    step = ExtractLongitude()
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {"latitude": 44.9816, "longitude": -93.2577},
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    result = step.execute(ctx, None)
    assert result == -93.2577


def test_extract_longitude_returns_none_when_missing():
    """ExtractLongitude returns None when longitude is absent."""
    step = ExtractLongitude()
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {"latitude": 44.9816},
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    result = step.execute(ctx, None)
    assert result is None


def test_extract_coordinates_returns_formatted_string_when_present():
    """ExtractCoordinates returns '<lat>, <lng>' when both are available."""
    step = ExtractCoordinates()
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {"latitude": 44.9816, "longitude": -93.2577},
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    result = step.execute(ctx, None)
    assert result == "44.9816, -93.2577"


def test_extract_coordinates_returns_none_when_lat_or_lng_missing():
    """ExtractCoordinates returns None when latitude or longitude is absent."""
    step = ExtractCoordinates()
    ctx_missing_lat = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {"longitude": -93.2577},
    })
    ctx_missing_lat.set("_global_pipeline_id", "gp")
    ctx_missing_lat.set("_current_stage_id", "s1")
    ctx_missing_lat.set("_current_pipeline_id", "p1")

    assert step.execute(ctx_missing_lat, None) is None

    ctx_missing_lng = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {"latitude": 44.9816},
    })
    ctx_missing_lng.set("_global_pipeline_id", "gp")
    ctx_missing_lng.set("_current_stage_id", "s1")
    ctx_missing_lng.set("_current_pipeline_id", "p1")

    assert step.execute(ctx_missing_lng, None) is None


def test_latitude_pipeline_sets_property():
    """LatitudePipeline extracts latitude and sets number property in context."""
    schema = PropertySchema(name="Latitude", type="number", options=None)
    pipeline = LatitudePipeline("Latitude", schema)
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {"latitude": 44.9816, "longitude": -93.2577},
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Latitude" in props
    assert props["Latitude"] == {"number": 44.9816}


def test_latitude_pipeline_omits_property_when_missing():
    """LatitudePipeline does not set property when latitude is absent."""
    schema = PropertySchema(name="Latitude", type="number", options=None)
    pipeline = LatitudePipeline("Latitude", schema)
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {"longitude": -93.2577},
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Latitude" not in props


def test_longitude_pipeline_sets_property():
    """LongitudePipeline extracts longitude and sets number property in context."""
    schema = PropertySchema(name="Longitude", type="number", options=None)
    pipeline = LongitudePipeline("Longitude", schema)
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {"latitude": 44.9816, "longitude": -93.2577},
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Longitude" in props
    assert props["Longitude"] == {"number": -93.2577}


def test_longitude_pipeline_omits_property_when_missing():
    """LongitudePipeline does not set property when longitude is absent."""
    schema = PropertySchema(name="Longitude", type="number", options=None)
    pipeline = LongitudePipeline("Longitude", schema)
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {"latitude": 44.9816},
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Longitude" not in props


def test_coordinates_pipeline_sets_property():
    """CoordinatesPipeline extracts '<lat>, <lng>' and sets rich_text property in context."""
    schema = PropertySchema(name="Coordinates", type="rich_text", options=None)
    pipeline = CoordinatesPipeline("Coordinates", schema)
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {"latitude": 44.9816, "longitude": -93.2577},
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Coordinates" in props
    assert props["Coordinates"] == {
        "rich_text": [
            {"type": "text", "text": {"content": "44.9816, -93.2577", "link": None}}
        ]
    }


def test_coordinates_pipeline_omits_property_when_missing():
    """CoordinatesPipeline does not set property when lat or lng is absent."""
    schema = PropertySchema(name="Coordinates", type="rich_text", options=None)
    pipeline = CoordinatesPipeline("Coordinates", schema)
    ctx = PipelineRunContext(run_id="r1", initial={
        CtxKeys.GOOGLE_PLACE: {"latitude": 44.9816},
    })
    ctx.set("_global_pipeline_id", "gp")
    ctx.set("_current_stage_id", "s1")
    ctx.set("_current_pipeline_id", "p1")

    _run_pipeline(pipeline, ctx, "r1", "s1")

    props = ctx.get_properties()
    assert "Coordinates" not in props
