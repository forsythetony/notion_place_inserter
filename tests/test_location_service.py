"""Unit tests for LocationService and LocationIndexCache."""

import time
from unittest.mock import MagicMock

import pytest

from app.models.location import LocationCandidate, LocationNode
from app.services.location_index_cache import LocationIndexCache
from app.services.location_service import LocationService


def _mock_page(page_id: str, name: str, type_: str | None = None, country: str | None = None, parent_id: str | None = None):
    props = {
        "Name": {"type": "title", "title": [{"plain_text": name}]},
        "Type": {"type": "select", "select": {"name": type_}} if type_ else {"type": "select", "select": None},
        "Country": {"type": "select", "select": {"name": country}} if country else {"type": "select", "select": None},
        "Parent item": {"type": "relation", "relation": [{"id": parent_id}]} if parent_id else {"type": "relation", "relation": []},
    }
    return {"id": page_id, "object": "page", "properties": props}


def test_location_index_cache_fetch_and_parse():
    """LocationIndexCache fetches pages and parses into LocationNode list."""
    mock_client = MagicMock()
    mock_client.data_sources.query.return_value = {
        "results": [
            _mock_page("p1", "Minneapolis", "City", "USA"),
            _mock_page("p2", "Minnesota", "State", "USA"),
        ],
        "has_more": False,
        "next_cursor": None,
    }

    def get_ds_id(name):
        return "ds-locations"

    cache = LocationIndexCache(mock_client, get_ds_id, ttl_seconds=300)
    nodes = cache.get()
    assert len(nodes) == 2
    assert nodes[0].page_id == "p1"
    assert nodes[0].name == "Minneapolis"
    assert nodes[0].type_ == "City"
    assert nodes[0].country == "USA"
    assert nodes[1].name == "Minnesota"


def test_location_index_cache_ttl():
    """LocationIndexCache returns cached entries within TTL, refetches after expiry."""
    mock_client = MagicMock()
    mock_client.data_sources.query.return_value = {
        "results": [_mock_page("p1", "Austin")],
        "has_more": False,
        "next_cursor": None,
    }

    def get_ds_id(name):
        return "ds-1"

    cache = LocationIndexCache(mock_client, get_ds_id, ttl_seconds=0.1)
    nodes1 = cache.get()
    nodes2 = cache.get()
    assert nodes1 == nodes2
    assert mock_client.data_sources.query.call_count == 1
    time.sleep(0.15)
    cache.get()
    assert mock_client.data_sources.query.call_count == 2


def test_location_index_cache_invalidate():
    """invalidate clears cache so next get fetches fresh."""
    mock_client = MagicMock()
    mock_client.data_sources.query.return_value = {
        "results": [_mock_page("p1", "Boston")],
        "has_more": False,
        "next_cursor": None,
    }

    def get_ds_id(name):
        return "ds-1"

    cache = LocationIndexCache(mock_client, get_ds_id, ttl_seconds=300)
    cache.get()
    cache.invalidate()
    cache.get()
    assert mock_client.data_sources.query.call_count == 2


def test_location_service_find_best_match():
    """LocationService.find_best_match returns matching node when present."""
    mock_notion = MagicMock()
    mock_notion.get_data_source_id.return_value = "ds-loc"
    mock_notion.client.data_sources.query.return_value = {
        "results": [
            _mock_page("p1", "Minneapolis", "City", "USA"),
            _mock_page("p2", "Saint Paul", "City", "USA"),
        ],
        "has_more": False,
        "next_cursor": None,
    }

    svc = LocationService(mock_notion, cache_ttl_seconds=300)
    candidate = LocationCandidate(display_name="Minneapolis", country="USA")
    result = svc.find_best_match(candidate)
    assert result is not None
    node, score, matched_by = result
    assert node.page_id == "p1"
    assert node.name == "Minneapolis"
    assert score >= 0.85
    assert matched_by in ("exact_name", "normalized_name")


def test_location_service_find_best_match_no_match():
    """LocationService.find_best_match returns None when no match."""
    mock_notion = MagicMock()
    mock_notion.get_data_source_id.return_value = "ds-loc"
    mock_notion.client.data_sources.query.return_value = {
        "results": [_mock_page("p1", "Austin", "City", "USA")],
        "has_more": False,
        "next_cursor": None,
    }

    svc = LocationService(mock_notion, cache_ttl_seconds=300)
    candidate = LocationCandidate(display_name="Unknown City", country="USA")
    result = svc.find_best_match(candidate)
    assert result is None


def test_location_service_resolve_or_create_matches_existing():
    """resolve_or_create returns matched resolution when location exists."""
    mock_notion = MagicMock()
    mock_notion.get_data_source_id.return_value = "ds-loc"
    mock_notion.client.data_sources.query.return_value = {
        "results": [_mock_page("p1", "Minneapolis", "City", "USA")],
        "has_more": False,
        "next_cursor": None,
    }

    svc = LocationService(mock_notion, cache_ttl_seconds=300)
    candidate = LocationCandidate(display_name="Minneapolis", country="USA")
    resolution = svc.resolve_or_create(candidate)
    assert resolution.resolution_mode == "matched"
    assert resolution.location_page_id == "p1"
    mock_notion.create_page.assert_not_called()


def test_location_service_resolve_or_create_creates_new():
    """resolve_or_create creates new location when no match and returns created resolution."""
    mock_notion = MagicMock()
    mock_notion.get_data_source_id.return_value = "ds-loc"
    mock_notion.client.data_sources.query.return_value = {
        "results": [],
        "has_more": False,
        "next_cursor": None,
    }
    mock_notion.create_page.return_value = {"id": "p-new"}

    svc = LocationService(mock_notion, cache_ttl_seconds=300)
    candidate = LocationCandidate(display_name="New City", country="USA")
    resolution = svc.resolve_or_create(candidate)
    assert resolution.resolution_mode == "created"
    assert resolution.location_page_id == "p-new"
    mock_notion.create_page.assert_called_once()
    call_props = mock_notion.create_page.call_args[1]["properties"]
    assert "Name" in call_props
    assert call_props["Name"]["title"][0]["text"]["content"] == "New City"


def test_location_service_resolve_or_create_with_parent():
    """resolve_or_create attaches parent when state exists and matches."""
    mock_notion = MagicMock()
    mock_notion.get_data_source_id.return_value = "ds-loc"
    mock_notion.client.data_sources.query.return_value = {
        "results": [
            _mock_page("p-state", "Minnesota", "State", "USA"),
            _mock_page("p-city", "Minneapolis", "City", "USA", parent_id="p-state"),
        ],
        "has_more": False,
        "next_cursor": None,
    }
    mock_notion.create_page.return_value = {"id": "p-new-city"}

    svc = LocationService(mock_notion, cache_ttl_seconds=300)
    candidate = LocationCandidate(
        display_name="Rochester",
        state_or_region="Minnesota",
        country="USA",
    )
    resolution = svc.resolve_or_create(candidate)
    assert resolution.resolution_mode == "created"
    assert resolution.location_page_id == "p-new-city"
    assert resolution.parent_page_id == "p-state"
    call_props = mock_notion.create_page.call_args[1]["properties"]
    assert "Parent item" in call_props
    assert call_props["Parent item"]["relation"][0]["id"] == "p-state"


def test_location_service_resolve_or_create_exact_match_does_not_call_claude():
    """Exact match wins without calling Claude."""
    mock_notion = MagicMock()
    mock_notion.get_data_source_id.return_value = "ds-loc"
    mock_notion.client.data_sources.query.return_value = {
        "results": [_mock_page("p1", "Minneapolis", "City", "USA")],
        "has_more": False,
        "next_cursor": None,
    }
    mock_claude = MagicMock()

    svc = LocationService(
        mock_notion,
        claude_service=mock_claude,
        cache_ttl_seconds=300,
    )
    candidate = LocationCandidate(display_name="Minneapolis", country="USA")
    resolution = svc.resolve_or_create(candidate)

    assert resolution is not None
    assert resolution.resolution_mode == "matched"
    assert resolution.location_page_id == "p1"
    mock_notion.create_page.assert_not_called()
    mock_claude.choose_option_from_context.assert_not_called()


def test_location_service_resolve_or_create_claude_fallback_selects_twin_cities():
    """Claude fallback selects Twin Cities, MN when candidate context indicates Minneapolis."""
    mock_notion = MagicMock()
    mock_notion.get_data_source_id.return_value = "ds-loc"
    mock_notion.client.data_sources.query.return_value = {
        "results": [
            _mock_page("p-twin", "Twin Cities, MN", "State", "USA"),
            _mock_page("p-other", "Saint Paul", "City", "USA"),
        ],
        "has_more": False,
        "next_cursor": None,
    }
    mock_claude = MagicMock()
    mock_claude.choose_option_from_context.return_value = "Twin Cities, MN"

    svc = LocationService(
        mock_notion,
        claude_service=mock_claude,
        cache_ttl_seconds=300,
    )
    candidate = LocationCandidate(
        display_name="Minneapolis",
        state_or_region="Minnesota",
        country="USA",
    )
    resolution = svc.resolve_or_create(
        candidate,
        google_place={"formattedAddress": "Minneapolis, MN, USA"},
    )

    assert resolution is not None
    assert resolution.resolution_mode == "matched"
    assert resolution.location_page_id == "p-twin"
    assert resolution.matched_by == "claude_constrained"
    mock_notion.create_page.assert_not_called()


def test_location_service_resolve_or_create_claude_fallback_no_match_still_creates():
    """Claude fallback returning no match still allows creation in normal mode."""
    mock_notion = MagicMock()
    mock_notion.get_data_source_id.return_value = "ds-loc"
    mock_notion.client.data_sources.query.return_value = {
        "results": [_mock_page("p1", "Austin", "City", "USA")],
        "has_more": False,
        "next_cursor": None,
    }
    mock_notion.create_page.return_value = {"id": "p-new"}
    mock_claude = MagicMock()
    mock_claude.choose_option_from_context.return_value = None

    svc = LocationService(
        mock_notion,
        claude_service=mock_claude,
        cache_ttl_seconds=300,
    )
    candidate = LocationCandidate(display_name="Unknown City", country="USA")
    resolution = svc.resolve_or_create(candidate)

    assert resolution is not None
    assert resolution.resolution_mode == "created"
    assert resolution.location_page_id == "p-new"
    mock_notion.create_page.assert_called_once()


def test_location_service_resolve_or_create_dry_run_returns_none_no_create():
    """Dry run returns None and never calls create_page when no existing location matches."""
    mock_notion = MagicMock()
    mock_notion.get_data_source_id.return_value = "ds-loc"
    mock_notion.client.data_sources.query.return_value = {
        "results": [_mock_page("p1", "Austin", "City", "USA")],
        "has_more": False,
        "next_cursor": None,
    }
    mock_claude = MagicMock()
    mock_claude.choose_option_from_context.return_value = None

    svc = LocationService(
        mock_notion,
        claude_service=mock_claude,
        cache_ttl_seconds=300,
    )
    candidate = LocationCandidate(display_name="New City", country="USA")
    resolution = svc.resolve_or_create(candidate, dry_run=True)

    assert resolution is None
    mock_notion.create_page.assert_not_called()


def test_location_service_resolve_or_create_dry_run_still_links_when_matched():
    """Dry run still allows linking to existing location when exact or Claude fallback succeeds."""
    mock_notion = MagicMock()
    mock_notion.get_data_source_id.return_value = "ds-loc"
    mock_notion.client.data_sources.query.return_value = {
        "results": [_mock_page("p1", "Minneapolis", "City", "USA")],
        "has_more": False,
        "next_cursor": None,
    }

    svc = LocationService(mock_notion, cache_ttl_seconds=300)
    candidate = LocationCandidate(display_name="Minneapolis", country="USA")
    resolution = svc.resolve_or_create(candidate, dry_run=True)

    assert resolution is not None
    assert resolution.resolution_mode == "matched"
    assert resolution.location_page_id == "p1"
    mock_notion.create_page.assert_not_called()
