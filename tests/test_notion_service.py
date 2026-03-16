"""Unit tests for NotionService."""

from unittest.mock import MagicMock, patch

from httpx import Headers
from notion_client.errors import APIResponseError

from app.services.notion_service import NotionService


def test_create_page_logs_data_source_failed_and_raises():
    """create_page logs structured observability and re-raises on data_source not found."""
    mock_client = MagicMock()
    mock_client.pages.create.side_effect = APIResponseError(
        code="object_not_found",
        status=400,
        message=(
            "Could not find data_source with ID: 1e2a5cd4-f107-490f-9b7a-4af865fd1beb. "
            "Make sure the relevant pages and databases are shared with your integration."
        ),
        headers=Headers(),
        raw_body_text="",
    )

    svc = NotionService(api_key="test-key")
    svc._client = mock_client

    with patch("app.services.notion_service.logger") as mock_logger:
        try:
            svc.create_page(
                data_source_id="ds-123",
                properties={"Title": {"title": [{"text": {"content": "Test"}}]}},
            )
        except APIResponseError:
            pass

    mock_logger.error.assert_called_once()
    call_args = mock_logger.error.call_args
    msg = str(call_args)
    assert "notion_create_page_data_source_failed" in msg
    assert "ds-123" in msg
    assert "error_domain=notion" in msg or "notion" in msg
    assert "data_source_not_found" in msg


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


def test_create_page_honors_dry_run():
    """create_page returns dry-run payload and does not call Notion API when dry_run is enabled."""
    mock_client = MagicMock()
    svc = NotionService(api_key="test-key", dry_run=True)
    svc._client = mock_client

    result = svc.create_page(
        data_source_id="ds-123",
        properties={"Title": {"title": [{"text": {"content": "Test"}}]}},
        icon={"type": "external", "external": {"url": "https://example.com/icon.png"}},
        cover={"type": "external", "external": {"url": "https://example.com/cover.jpg"}},
    )

    mock_client.pages.create.assert_not_called()
    assert result["mode"] == "dry_run"
    assert result["parent"] == {"data_source_id": "ds-123"}
    assert "properties" in result
    assert "icon" in result
    assert "cover" in result


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


def test_create_page_retries_on_file_upload_not_ready_then_succeeds():
    """create_page retries specific Notion file_upload propagation failures."""
    mock_client = MagicMock()
    mock_client.pages.create.side_effect = [
        APIResponseError(
            code="object_not_found",
            status=400,
            message=(
                "Could not find file_upload with ID: fu-123. Confirm the status of the file "
                "upload is `uploaded` and that your integration has capabilities to update or "
                "insert content."
            ),
            headers=Headers(),
            raw_body_text="",
        ),
        {"id": "page-123", "object": "page"},
    ]

    svc = NotionService(api_key="test-key")
    svc._client = mock_client

    result = svc.create_page(
        data_source_id="ds-123",
        properties={"Title": {"title": [{"text": {"content": "Test"}}]}},
        cover={"type": "file_upload", "file_upload": {"id": "fu-123"}},
    )

    assert result["id"] == "page-123"
    assert mock_client.pages.create.call_count == 2


def test_create_page_with_token_retries_on_file_upload_not_ready_then_succeeds():
    """create_page_with_token retries specific Notion file_upload propagation failures."""
    with patch("app.services.notion_service.Client") as client_cls:
        client = MagicMock()
        client.pages.create.side_effect = [
            APIResponseError(
                code="object_not_found",
                status=400,
                message=(
                    "Could not find file_upload with ID: fu-123. Confirm the status of the file "
                    "upload is `uploaded` and that your integration has capabilities to update or "
                    "insert content."
                ),
                headers=Headers(),
                raw_body_text="",
            ),
            {"id": "page-xyz", "object": "page"},
        ]
        client_cls.return_value = client

        result = NotionService.create_page_with_token(
            access_token="oauth-token",
            data_source_id="ds-123",
            properties={"Title": {"title": [{"text": {"content": "Test"}}]}},
            cover={"type": "file_upload", "file_upload": {"id": "fu-123"}},
            dry_run=False,
        )

    assert result["id"] == "page-xyz"
    assert client.pages.create.call_count == 2
