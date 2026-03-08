"""Unit tests for NotionService."""

from unittest.mock import MagicMock

from app.services.notion_service import NotionService


def test_create_page_includes_icon_and_cover_when_provided():
    """create_page passes icon and cover to the Notion API when provided."""
    mock_client = MagicMock()
    mock_client.pages.create.return_value = {"id": "page-123", "object": "page"}

    svc = NotionService(api_key="test-key")
    svc._client = mock_client

    svc.create_page(
        data_source_id="ds-123",
        properties={"Title": {"title": [{"text": {"content": "Test"}}]}},
        icon={"type": "emoji", "emoji": "🌉"},
        cover={"type": "external", "external": {"url": "https://example.com/cover.jpg"}},
    )

    mock_client.pages.create.assert_called_once()
    call_kwargs = mock_client.pages.create.call_args[1]
    assert call_kwargs["icon"] == {"type": "emoji", "emoji": "🌉"}
    assert call_kwargs["cover"] == {"type": "external", "external": {"url": "https://example.com/cover.jpg"}}
    assert "parent" in call_kwargs
    assert "properties" in call_kwargs


def test_create_page_omits_icon_cover_when_not_provided():
    """create_page does not include icon or cover when not provided."""
    mock_client = MagicMock()
    mock_client.pages.create.return_value = {"id": "page-123", "object": "page"}

    svc = NotionService(api_key="test-key")
    svc._client = mock_client

    svc.create_page(
        data_source_id="ds-123",
        properties={"Title": {"title": [{"text": {"content": "Test"}}]}},
    )

    call_kwargs = mock_client.pages.create.call_args[1]
    assert "icon" not in call_kwargs
    assert "cover" not in call_kwargs
    assert "parent" in call_kwargs
    assert "properties" in call_kwargs


def test_upload_cover_from_bytes_returns_success_when_already_uploaded_after_send():
    """If retrieve returns uploaded right after send, skip complete and succeed."""
    mock_client = MagicMock()
    mock_client.file_uploads.create.return_value = {"id": "fu-123"}
    mock_client.file_uploads.retrieve.return_value = {"status": "uploaded"}

    svc = NotionService(api_key="test-key")
    svc._client = mock_client

    result = svc.upload_cover_from_bytes(
        b"image-bytes",
        poll_interval=0,
        poll_max_attempts=1,
    )

    assert result == {"type": "file_upload", "file_upload": {"id": "fu-123"}}
    mock_client.file_uploads.send.assert_called_once()
    mock_client.file_uploads.complete.assert_not_called()


def test_upload_cover_from_bytes_completes_when_pending_then_uploaded():
    """If retrieve shows pending, complete is called and then uploaded returns success."""
    mock_client = MagicMock()
    mock_client.file_uploads.create.return_value = {"id": "fu-123"}
    mock_client.file_uploads.retrieve.side_effect = [
        {"status": "pending"},
        {"status": "uploaded"},
    ]

    svc = NotionService(api_key="test-key")
    svc._client = mock_client

    result = svc.upload_cover_from_bytes(
        b"image-bytes",
        poll_interval=0,
        poll_max_attempts=1,
    )

    assert result == {"type": "file_upload", "file_upload": {"id": "fu-123"}}
    mock_client.file_uploads.send.assert_called_once()
    mock_client.file_uploads.complete.assert_called_once_with("fu-123")
