"""Unit tests for WhatsAppService send behavior."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.whatsapp_service import WhatsAppService, WhatsAppServiceError


def test_whatsapp_service_requires_credentials():
    """WhatsAppService raises when credentials are missing."""
    with pytest.raises(ValueError, match="TWILIO_ACCOUNT_SID"):
        WhatsAppService(
            account_sid="",
            auth_token="token",
            from_number="whatsapp:+14155238886",
        )
    with pytest.raises(ValueError, match="TWILIO_AUTH_TOKEN"):
        WhatsAppService(
            account_sid="sid",
            auth_token="",
            from_number="whatsapp:+14155238886",
        )
    with pytest.raises(ValueError, match="TWILIO_WHATSAPP_NUMBER"):
        WhatsAppService(
            account_sid="sid",
            auth_token="token",
            from_number="",
        )
    with pytest.raises(ValueError, match="whatsapp:"):
        WhatsAppService(
            account_sid="sid",
            auth_token="token",
            from_number="+14155238886",
        )


def test_send_message_requires_whatsapp_format():
    """send_message rejects invalid to_number format."""
    with patch("app.services.whatsapp_service.Client") as mock_client:
        mock_client.return_value.messages.create.return_value.sid = "SM123"
        svc = WhatsAppService(
            account_sid="AC123",
            auth_token="token",
            from_number="whatsapp:+14155238886",
        )
        with pytest.raises(ValueError, match="whatsapp:"):
            svc.send_message(to_number="+15551234567", body="Hi")
        with pytest.raises(ValueError, match="whatsapp:"):
            svc.send_message(to_number="", body="Hi")


@patch("app.services.whatsapp_service.Client")
def test_send_message_returns_sid(mock_client):
    """send_message returns Twilio message SID on success."""
    mock_msg = MagicMock()
    mock_msg.sid = "SMabc123"
    mock_client.return_value.messages.create.return_value = mock_msg

    svc = WhatsAppService(
        account_sid="AC123",
        auth_token="token",
        from_number="whatsapp:+14155238886",
    )
    sid = svc.send_message(to_number="whatsapp:+15551234567", body="Hi there")
    assert sid == "SMabc123"
    mock_client.return_value.messages.create.assert_called_once_with(
        from_="whatsapp:+14155238886",
        to="whatsapp:+15551234567",
        body="Hi there",
    )


@patch("app.services.whatsapp_service.Client")
def test_send_message_raises_on_twilio_error(mock_client):
    """send_message raises WhatsAppServiceError when Twilio fails."""
    mock_client.return_value.messages.create.side_effect = Exception("Twilio error")

    svc = WhatsAppService(
        account_sid="AC123",
        auth_token="token",
        from_number="whatsapp:+14155238886",
    )
    with pytest.raises(WhatsAppServiceError, match="WhatsApp send failed"):
        svc.send_message(to_number="whatsapp:+15551234567", body="Hi")
