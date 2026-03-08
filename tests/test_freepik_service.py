"""Unit tests for FreepikService."""

from unittest.mock import MagicMock, patch

from app.services.freepik_service import FreepikService


def test_search_icons_returns_empty_when_term_empty():
    """search_icons returns empty list when term is empty."""
    svc = FreepikService(api_key="test-key")
    with patch.object(svc._client, "get") as mock_get:
        result = svc.search_icons("")
    assert result == []
    mock_get.assert_not_called()


def test_search_icons_returns_empty_on_exception():
    """search_icons returns empty list on HTTP or parse error."""
    svc = FreepikService(api_key="test-key")
    with patch.object(svc._client, "get", side_effect=Exception("network error")):
        result = svc.search_icons("bridge")
    assert result == []


def test_search_icons_returns_data_from_response():
    """search_icons returns data array from API response."""
    svc = FreepikService(api_key="test-key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {
                "id": 123,
                "thumbnails": [
                    {"url": "https://cdn.freepik.com/icon.png", "width": 128, "height": 128},
                ],
            },
        ],
    }
    with patch.object(svc._client, "get", return_value=mock_response) as mock_get:
        result = svc.search_icons("bridge")
    assert len(result) == 1
    assert result[0]["id"] == 123
    mock_response.raise_for_status.assert_called_once()
    call_kwargs = mock_get.call_args[1]
    assert call_kwargs["headers"]["x-freepik-api-key"] == "test-key"
    assert call_kwargs["params"]["term"] == "bridge"
    assert call_kwargs["params"]["per_page"] == 1


def test_get_first_icon_url_returns_url_when_results():
    """get_first_icon_url returns thumbnail URL of first result."""
    svc = FreepikService(api_key="test-key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {
                "thumbnails": [
                    {"url": "https://cdn.freepik.com/icon-128.png", "width": 128, "height": 128},
                    {"url": "https://cdn.freepik.com/icon-512.png", "width": 512, "height": 512},
                ],
            },
        ],
    }
    with patch.object(svc._client, "get", return_value=mock_response):
        url = svc.get_first_icon_url("bridge")
    assert url == "https://cdn.freepik.com/icon-512.png"


def test_get_first_icon_url_returns_none_when_no_results():
    """get_first_icon_url returns None when no icons returned."""
    svc = FreepikService(api_key="test-key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"data": []}
    with patch.object(svc._client, "get", return_value=mock_response):
        url = svc.get_first_icon_url("xyznonexistent")
    assert url is None


def test_get_first_icon_url_returns_none_when_no_thumbnails():
    """get_first_icon_url returns None when first icon has no thumbnails."""
    svc = FreepikService(api_key="test-key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "data": [{"id": 1, "thumbnails": []}],
    }
    with patch.object(svc._client, "get", return_value=mock_response):
        url = svc.get_first_icon_url("bridge")
    assert url is None


def test_get_first_icon_url_falls_back_to_nested_url_fields():
    """get_first_icon_url extracts a nested URL when thumbnails are absent."""
    svc = FreepikService(api_key="test-key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {
                "id": 321,
                "thumbnails": [],
                "assets": {
                    "preview": {
                        "url": "https://cdn.freepik.com/fallback-icon.png",
                    }
                },
            }
        ]
    }
    with patch.object(svc._client, "get", return_value=mock_response):
        url = svc.get_first_icon_url("bridge")
    assert url == "https://cdn.freepik.com/fallback-icon.png"
