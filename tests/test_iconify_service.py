"""Tests for Iconify public API wrapper."""

from unittest.mock import MagicMock, patch

from app.services.iconify_service import IconifyService, icon_id_to_svg_url


def test_icon_id_to_svg_url_splits_collection_and_name():
    assert (
        icon_id_to_svg_url("material-symbols-light:ramen-dining-outline")
        == "https://api.iconify.design/material-symbols-light/ramen-dining-outline.svg"
    )


def test_icon_id_to_svg_url_single_segment_fallback():
    assert icon_id_to_svg_url("foo") == "https://api.iconify.design/foo.svg"


@patch("app.services.iconify_service.httpx.Client")
def test_iconify_get_first_icon_svg_url(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"icons": ["mdi:food-ramen"], "total": 1}
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    svc = IconifyService()
    url = svc.get_first_icon_svg_url("ramen")
    assert url == "https://api.iconify.design/mdi/food-ramen.svg"
    mock_client.get.assert_called_once()
    _args, kwargs = mock_client.get.call_args
    assert kwargs.get("params", {}).get("query") == "ramen"


@patch("app.services.iconify_service.httpx.Client")
def test_iconify_search_icons_empty_term(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    svc = IconifyService()
    assert svc.search_icons("") == []
    assert svc.search_icons("   ") == []
    mock_client.get.assert_not_called()
