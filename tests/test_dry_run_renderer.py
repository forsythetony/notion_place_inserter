"""Unit tests for dry-run table rendering and JSON response contract."""

import io

import pytest
from rich.console import Console

from app.services.dry_run_renderer import render_dry_run_table
from app.services.places_service import PLACES_DB_NAME, PlacesService


def test_render_dry_run_table_includes_property_name_type_value():
    """render_dry_run_table prints a table with Property, Type, Value, and Resolved By columns."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False)

    properties = {
        "Title": {"title": [{"type": "text", "text": {"content": "Stone Arch Bridge", "link": None}}]},
        "Address": {"rich_text": [{"type": "text", "text": {"content": "1 Main St, Minneapolis", "link": None}}]},
        "Website": {"url": "https://stonearchbridge.org"},
    }

    render_dry_run_table(PLACES_DB_NAME, properties, keywords="stone arch bridge", console=console)

    output = buf.getvalue()
    assert "Dry Run" in output
    assert "Resolved By" in output
    assert PLACES_DB_NAME in output
    assert "Title" in output
    assert "Stone Arch Bridge" in output
    assert "Address" in output
    assert "1 Main St, Minneapolis" in output
    assert "Website" in output
    assert "https://stonearchbridge.org" in output
    assert "title" in output
    assert "rich_text" in output
    assert "url" in output
    assert "stone arch bridge" in output


def test_render_dry_run_table_shows_resolved_by_pipeline():
    """render_dry_run_table displays pipeline_id in Resolved By column when property_sources provided."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False)

    properties = {
        "Title": {"title": [{"type": "text", "text": {"content": "Test", "link": None}}]},
        "Address": {"rich_text": [{"type": "text", "text": {"content": "123 Main St", "link": None}}]},
    }
    property_sources = {
        "Title": "title_Title",
        "Address": "address_Address",
    }

    render_dry_run_table(
        PLACES_DB_NAME,
        properties,
        keywords=None,
        property_sources=property_sources,
        console=console,
    )

    output = buf.getvalue()
    assert "Resolved By" in output
    assert "title_Title" in output
    assert "address_Address" in output


def test_render_dry_run_table_without_keywords():
    """render_dry_run_table works when keywords is None (e.g. randomLocation)."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False)

    properties = {"Title": {"title": [{"type": "text", "text": {"content": "Random Place", "link": None}}]}}
    render_dry_run_table(PLACES_DB_NAME, properties, keywords=None, console=console)

    output = buf.getvalue()
    assert PLACES_DB_NAME in output
    assert "Title" in output
    assert "Random Place" in output


def test_render_dry_run_table_relation_shows_notion_link():
    """render_dry_run_table displays relation properties as Notion page URLs (clickable in terminal)."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False)

    page_id = "544d5797-9344-4258-aed6-1f72e66b6927"
    properties = {
        "Title": {"title": [{"type": "text", "text": {"content": "Test Place", "link": None}}]},
        "Location": {"relation": [{"id": page_id}]},
    }

    render_dry_run_table(PLACES_DB_NAME, properties, keywords=None, console=console)

    output = buf.getvalue()
    assert "Location" in output
    assert "relation" in output
    assert "notion.so" in output
    assert "544d5797" in output  # page_id prefix (table may truncate full UUID)


def test_render_dry_run_table_relation_empty_shows_dash():
    """render_dry_run_table shows — for empty relation list."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False)
    properties = {"Location": {"relation": []}}
    render_dry_run_table(PLACES_DB_NAME, properties, keywords=None, console=console)
    output = buf.getvalue()
    assert "Location" in output
    assert "—" in output


def test_render_dry_run_table_shows_skipped_properties():
    """render_dry_run_table includes rows for NoOp-skipped properties with (skipped) indicator."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False)

    properties = {
        "Title": {"title": [{"type": "text", "text": {"content": "Test Place", "link": None}}]},
    }
    property_skips = {"Yelp": "noop_Yelp"}

    render_dry_run_table(
        PLACES_DB_NAME,
        properties,
        keywords=None,
        property_skips=property_skips,
        console=console,
    )

    output = buf.getvalue()
    assert "Yelp" in output
    assert "(skipped)" in output
    assert "noop_Yelp" in output


def test_places_service_dry_run_preserves_json_response_structure():
    """PlacesService dry-run returns the same JSON shape as before (mode, database, properties, summary)."""
    from unittest.mock import MagicMock, patch

    mock_notion = MagicMock()
    svc = PlacesService(notion_service=mock_notion, dry_run=True)

    entry = {
        "Title": {"title": [{"type": "text", "text": {"content": "Test Place", "link": None}}]},
    }

    with patch("app.services.places_service.render_dry_run_table") as mock_render:
        result = svc.create_place(entry, keywords="test keywords")

    mock_render.assert_called_once_with(
        PLACES_DB_NAME,
        entry,
        keywords="test keywords",
        property_sources=None,
        property_skips=None,
        icon=None,
        cover=None,
    )
    assert result["mode"] == "dry_run"
    assert result["database"] == PLACES_DB_NAME
    assert "properties" in result
    assert result["properties"] == entry
    assert "summary" in result
    assert result["summary"]["property_count"] == 1
    assert result["summary"]["property_names"] == ["Title"]
    assert result["keywords"] == "test keywords"


def test_places_service_dry_run_without_keywords_omits_keywords_field():
    """Dry-run for randomLocation (no keywords) omits keywords from response."""
    from unittest.mock import MagicMock, patch

    mock_notion = MagicMock()
    svc = PlacesService(notion_service=mock_notion, dry_run=True)
    entry = {"Title": {"title": [{"type": "text", "text": {"content": "Random", "link": None}}]}}

    with patch("app.services.places_service.render_dry_run_table"):
        result = svc.create_place(entry, keywords=None)

    assert "keywords" not in result
    assert result["mode"] == "dry_run"


def test_places_service_dry_run_includes_icon_cover_when_provided():
    """Dry-run response includes icon and cover when passed to create_place."""
    from unittest.mock import MagicMock, patch

    mock_notion = MagicMock()
    svc = PlacesService(notion_service=mock_notion, dry_run=True)
    entry = {"Title": {"title": [{"type": "text", "text": {"content": "Test", "link": None}}]}}
    icon = {"type": "external", "external": {"url": "https://cdn.freepik.com/icon/bridge.png"}}
    cover = {"type": "external", "external": {"url": "https://example.com/cover.jpg"}}

    with patch("app.services.places_service.render_dry_run_table"):
        result = svc.create_place(entry, keywords="bridge", icon=icon, cover=cover)

    assert result["icon"] == icon
    assert result["cover"] == cover
    assert result["mode"] == "dry_run"


def test_render_dry_run_table_includes_icon_and_cover_rows():
    """render_dry_run_table displays Icon and Cover rows when provided."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False)

    properties = {"Title": {"title": [{"type": "text", "text": {"content": "Stone Arch Bridge", "link": None}}]}}
    icon = {"type": "external", "external": {"url": "https://cdn.freepik.com/icon/bridge.png"}}
    cover = {"type": "external", "external": {"url": "https://lh3.googleusercontent.com/photo.jpg"}}

    render_dry_run_table(
        PLACES_DB_NAME,
        properties,
        keywords="stone arch bridge",
        icon=icon,
        cover=cover,
        console=console,
    )

    output = buf.getvalue()
    assert "Icon" in output
    assert "freepik" in output or "bridge.png" in output
    assert "Cover" in output
    assert "photo.jpg" in output or "lh3.googleusercontent" in output
    assert "resolve_icon_emoji" in output
    assert "resolve_cover_image" in output


def test_render_dry_run_table_shows_skipped_for_icon_cover_when_absent():
    """render_dry_run_table shows (skipped) for Icon and Cover when not provided."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False)

    properties = {"Title": {"title": [{"type": "text", "text": {"content": "Test", "link": None}}]}}

    render_dry_run_table(
        PLACES_DB_NAME,
        properties,
        icon=None,
        cover=None,
        console=console,
    )

    output = buf.getvalue()
    assert "Icon" in output
    assert "Cover" in output
    # Both should show (skipped)
    assert output.count("(skipped)") >= 2


def test_places_service_create_place_passes_icon_cover_to_notion_when_not_dry_run():
    """create_place forwards icon and cover to NotionService.create_page when not in dry run."""
    from unittest.mock import MagicMock

    mock_notion = MagicMock()
    mock_notion.get_data_source_id.return_value = "ds-123"
    mock_notion.create_page.return_value = {"id": "page-456", "object": "page"}

    svc = PlacesService(notion_service=mock_notion, dry_run=False)
    entry = {"Title": {"title": [{"type": "text", "text": {"content": "Test", "link": None}}]}}
    icon = {"type": "external", "external": {"url": "https://cdn.freepik.com/icon/museum.png"}}
    cover = {"type": "external", "external": {"url": "https://example.com/cover.jpg"}}

    svc.create_place(entry, icon=icon, cover=cover)

    mock_notion.create_page.assert_called_once_with(
        data_source_id="ds-123",
        properties=entry,
        icon=icon,
        cover=cover,
    )
