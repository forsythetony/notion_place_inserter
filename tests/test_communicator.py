"""Unit tests for Communicator message formatting and policy."""

from unittest.mock import MagicMock

import pytest

from app.queue.models import PipelineFailureEvent, PipelineSuccessEvent
from app.services.communicator import Communicator
from app.services.whatsapp_service import WhatsAppService, WhatsAppServiceError


@pytest.fixture
def mock_whatsapp():
    """Mock WhatsAppService that records sent messages."""
    m = MagicMock(spec=WhatsAppService)
    m.send_message = MagicMock(return_value="SM123")
    return m


def test_notify_pipeline_success_sends_with_url(mock_whatsapp):
    """Success notification includes Notion URL when present."""
    comm = Communicator(
        mock_whatsapp,
        enabled=True,
        default_recipient="whatsapp:+15551234567",
    )
    event = PipelineSuccessEvent(
        job_id="loc_1",
        run_id="run_1",
        keywords="stone arch bridge minneapolis",
        result={"url": "https://www.notion.so/abc123"},
        recipient_whatsapp=None,
    )
    comm.notify_pipeline_success(event)
    mock_whatsapp.send_message.assert_called_once()
    call = mock_whatsapp.send_message.call_args
    assert call.kwargs["to_number"] == "whatsapp:+15551234567"
    assert "Done: created your place page" in call.kwargs["body"]
    assert "stone arch bridge minneapolis" in call.kwargs["body"]
    assert "https://www.notion.so/abc123" in call.kwargs["body"]


def test_notify_pipeline_success_fallback_when_no_url(mock_whatsapp):
    """Success notification uses fallback when result has no URL (e.g. dry run)."""
    comm = Communicator(
        mock_whatsapp,
        enabled=True,
        default_recipient="whatsapp:+15551234567",
    )
    event = PipelineSuccessEvent(
        job_id="loc_1",
        run_id="run_1",
        keywords="test place",
        result={"mode": "dry_run", "database": "Places to Visit"},
        recipient_whatsapp=None,
    )
    comm.notify_pipeline_success(event)
    mock_whatsapp.send_message.assert_called_once()
    assert "(page created)" in mock_whatsapp.send_message.call_args.kwargs["body"]


def test_notify_pipeline_success_uses_event_recipient_over_default(mock_whatsapp):
    """Success uses event.recipient_whatsapp when provided."""
    comm = Communicator(
        mock_whatsapp,
        enabled=True,
        default_recipient="whatsapp:+15551111111",
    )
    event = PipelineSuccessEvent(
        job_id="loc_1",
        run_id="run_1",
        keywords="place",
        result={"url": "https://notion.so/x"},
        recipient_whatsapp="whatsapp:+15551234567",
    )
    comm.notify_pipeline_success(event)
    mock_whatsapp.send_message.assert_called_once_with(
        to_number="whatsapp:+15551234567",
        body='Done: created your place page for "place". https://notion.so/x',
    )


def test_notify_pipeline_success_skips_when_no_recipient(mock_whatsapp):
    """Success notification skipped when no recipient and no default."""
    comm = Communicator(
        mock_whatsapp,
        enabled=True,
        default_recipient=None,
    )
    event = PipelineSuccessEvent(
        job_id="loc_1",
        run_id="run_1",
        keywords="place",
        result={"url": "https://notion.so/x"},
        recipient_whatsapp=None,
    )
    comm.notify_pipeline_success(event)
    mock_whatsapp.send_message.assert_not_called()


def test_notify_pipeline_success_skips_when_disabled(mock_whatsapp):
    """Success notification skipped when WHATSAPP_STATUS_ENABLED=0."""
    comm = Communicator(
        mock_whatsapp,
        enabled=False,
        default_recipient="whatsapp:+15551234567",
    )
    event = PipelineSuccessEvent(
        job_id="loc_1",
        run_id="run_1",
        keywords="place",
        result={"url": "https://notion.so/x"},
        recipient_whatsapp=None,
    )
    comm.notify_pipeline_success(event)
    mock_whatsapp.send_message.assert_not_called()


def test_notify_pipeline_failure_sends_truncated_error(mock_whatsapp):
    """Failure notification truncates long errors."""
    comm = Communicator(
        mock_whatsapp,
        enabled=True,
        default_recipient="whatsapp:+15551234567",
        max_error_chars=50,
    )
    long_error = "Something went wrong: " + "x" * 200
    event = PipelineFailureEvent(
        job_id="loc_1",
        run_id="run_1",
        keywords="bad place",
        error=ValueError(long_error),
        recipient_whatsapp=None,
    )
    comm.notify_pipeline_failure(event)
    mock_whatsapp.send_message.assert_called_once()
    body = mock_whatsapp.send_message.call_args.kwargs["body"]
    assert "Could not create a page for \"bad place\"" in body
    assert "Error:" in body
    assert body.endswith("...")
    assert len(body) < 150  # truncated


def test_notify_pipeline_failure_sanitizes_secrets(mock_whatsapp):
    """Failure notification redacts secret patterns."""
    comm = Communicator(
        mock_whatsapp,
        enabled=True,
        default_recipient="whatsapp:+15551234567",
    )
    event = PipelineFailureEvent(
        job_id="loc_1",
        run_id="run_1",
        keywords="place",
        error=ValueError("Auth failed: secret_abc123xyz"),
        recipient_whatsapp=None,
    )
    comm.notify_pipeline_failure(event)
    mock_whatsapp.send_message.assert_called_once()
    body = mock_whatsapp.send_message.call_args.kwargs["body"]
    assert "secret_abc123xyz" not in body
    assert "secret_***" in body


def test_notify_pipeline_failure_does_not_crash_on_send_error(mock_whatsapp):
    """Communicator logs but does not raise when WhatsApp send fails."""
    mock_whatsapp.send_message.side_effect = WhatsAppServiceError("Twilio error")
    comm = Communicator(
        mock_whatsapp,
        enabled=True,
        default_recipient="whatsapp:+15551234567",
    )
    event = PipelineFailureEvent(
        job_id="loc_1",
        run_id="run_1",
        keywords="place",
        error="Something failed",
        recipient_whatsapp=None,
    )
    comm.notify_pipeline_failure(event)  # should not raise
