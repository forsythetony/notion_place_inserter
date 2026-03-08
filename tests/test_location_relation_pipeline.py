"""Unit tests for location relation pipeline steps."""

from unittest.mock import MagicMock

import pytest

from app.models.location import LocationCandidate, LocationResolution
from app.pipeline_lib.context import ContextKeys, PipelineRunContext
from app.pipeline_lib.steps.location_relation import (
    BuildLocationCandidateStep,
    FormatLocationRelationForNotionStep,
    ResolveLocationRelationStep,
    _extract_from_address_components,
)


def test_extract_from_address_components():
    """_extract_from_address_components extracts locality, state, country."""
    components = [
        {"types": ["locality"], "longText": "Minneapolis"},
        {"types": ["administrative_area_level_1"], "longText": "Minnesota"},
        {"types": ["country"], "shortText": "US"},
    ]
    locality, state, country = _extract_from_address_components(components)
    assert locality == "Minneapolis"
    assert state == "Minnesota"
    assert country == "US"


def test_build_location_candidate_step_from_google_place():
    """BuildLocationCandidateStep builds candidate from GOOGLE_PLACE."""
    context = PipelineRunContext(
        run_id="r1",
        initial={
            ContextKeys.GOOGLE_PLACE: {
                "displayName": "Stone Arch Bridge",
                "addressComponents": [
                    {"types": ["locality"], "longText": "Minneapolis"},
                    {"types": ["administrative_area_level_1"], "longText": "Minnesota"},
                    {"types": ["country"], "shortText": "USA"},
                ],
                "id": "place-123",
            },
        },
    )
    step = BuildLocationCandidateStep("Location")
    result = step.execute(context, None)
    assert result is not None
    assert isinstance(result, LocationCandidate)
    assert result.display_name == "Minneapolis"
    assert result.state_or_region == "Minnesota"
    assert result.country == "USA"
    assert result.google_place_id == "place-123"


def test_build_location_candidate_step_fallback_to_query():
    """BuildLocationCandidateStep falls back to raw query when no place."""
    context = PipelineRunContext(
        run_id="r1",
        initial={
            ContextKeys.RAW_QUERY: "stone arch bridge minneapolis",
        },
    )
    step = BuildLocationCandidateStep("Location")
    result = step.execute(context, None)
    assert result is not None
    assert result.display_name == "stone arch bridge minneapolis"


def test_build_location_candidate_step_returns_none_when_empty():
    """BuildLocationCandidateStep returns None when no place and no query."""
    context = PipelineRunContext(run_id="r1", initial={})
    step = BuildLocationCandidateStep("Location")
    result = step.execute(context, None)
    assert result is None


def test_resolve_location_relation_step_calls_service():
    """ResolveLocationRelationStep calls LocationService.resolve_or_create."""
    resolution = LocationResolution(
        location_page_id="p1",
        resolution_mode="matched",
        matched_score=1.0,
        matched_by="exact_name",
    )
    mock_location_svc = MagicMock()
    mock_location_svc.resolve_or_create.return_value = resolution

    context = PipelineRunContext(
        run_id="r1",
        initial={"_location_service": mock_location_svc},
    )
    candidate = LocationCandidate(display_name="Minneapolis", country="USA")
    step = ResolveLocationRelationStep("Location")
    result = step.execute(context, candidate)

    mock_location_svc.resolve_or_create.assert_called_once_with(
        candidate, dry_run=False, google_place=None
    )
    assert result == resolution
    assert context.get("_location_resolution") == resolution


def test_resolve_location_relation_step_skips_when_no_service():
    """ResolveLocationRelationStep returns None when no location service."""
    context = PipelineRunContext(run_id="r1", initial={})
    candidate = LocationCandidate(display_name="Minneapolis")
    step = ResolveLocationRelationStep("Location")
    result = step.execute(context, candidate)
    assert result is None


def test_format_location_relation_for_notion_step():
    """FormatLocationRelationForNotionStep outputs Notion relation payload."""
    resolution = LocationResolution(
        location_page_id="page-uuid-123",
        resolution_mode="matched",
    )
    context = PipelineRunContext(run_id="r1", initial={})

    step = FormatLocationRelationForNotionStep("Location")
    result = step.execute(context, resolution)

    expected = {"relation": [{"id": "page-uuid-123"}]}
    assert result == expected
    assert context.get_properties().get("Location") == expected


def test_format_location_relation_returns_none_for_none_resolution():
    """FormatLocationRelationForNotionStep returns None when resolution is None."""
    context = PipelineRunContext(run_id="r1", initial={})
    step = FormatLocationRelationForNotionStep("Location")
    result = step.execute(context, None)
    assert result is None


def test_resolve_location_relation_step_dry_run_returns_none_when_would_create():
    """ResolveLocationRelationStep returns None in dry run when no match and would create."""
    mock_location_svc = MagicMock()
    mock_location_svc.resolve_or_create.return_value = None

    context = PipelineRunContext(
        run_id="r1",
        initial={
            "_location_service": mock_location_svc,
            "_dry_run": True,
        },
    )
    candidate = LocationCandidate(display_name="New City", country="USA")
    step = ResolveLocationRelationStep("Location")
    result = step.execute(context, candidate)

    assert result is None
    mock_location_svc.resolve_or_create.assert_called_once_with(
        candidate, dry_run=True, google_place=None
    )


def test_resolve_location_relation_step_dry_run_still_links_when_matched():
    """ResolveLocationRelationStep returns resolution in dry run when location matches."""
    resolution = LocationResolution(
        location_page_id="p1",
        resolution_mode="matched",
        matched_score=1.0,
        matched_by="exact_name",
    )
    mock_location_svc = MagicMock()
    mock_location_svc.resolve_or_create.return_value = resolution

    context = PipelineRunContext(
        run_id="r1",
        initial={
            "_location_service": mock_location_svc,
            "_dry_run": True,
        },
    )
    candidate = LocationCandidate(display_name="Minneapolis", country="USA")
    step = ResolveLocationRelationStep("Location")
    result = step.execute(context, candidate)

    assert result == resolution
    mock_location_svc.resolve_or_create.assert_called_once_with(
        candidate, dry_run=True, google_place=None
    )
