"""Twilio WhatsApp transport adapter for outbound run-status notifications."""

from loguru import logger
from twilio.rest import Client


class WhatsAppServiceError(Exception):
    """Raised when WhatsApp send fails (network, auth, rate limit, etc.)."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class WhatsAppService:
    """
    Transport adapter for Twilio WhatsApp.
    Owns Twilio client initialization and credential validation.
    Sends outbound WhatsApp text messages.
    """

    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        from_number: str,
    ) -> None:
        if not account_sid or not auth_token:
            raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are required")
        if not from_number or not from_number.startswith("whatsapp:"):
            raise ValueError(
                "TWILIO_WHATSAPP_NUMBER is required and must start with whatsapp:"
            )
        self._client = Client(account_sid, auth_token)
        self._from_number = from_number

    def send_message(self, *, to_number: str, body: str) -> str:
        """
        Send an outbound WhatsApp text message.
        Returns the provider message SID on success.
        Raises WhatsAppServiceError on failure.
        """
        if not to_number or not to_number.startswith("whatsapp:"):
            raise ValueError("to_number must be a WhatsApp number (whatsapp:+...)")
        try:
            msg = self._client.messages.create(
                from_=self._from_number,
                to=to_number,
                body=body,
            )
            sid = msg.sid
            logger.debug("whatsapp_sent", to=to_number, sid=sid)
            return sid
        except Exception as e:
            logger.warning("whatsapp_send_failed", to=to_number, error=str(e))
            raise WhatsAppServiceError(f"WhatsApp send failed: {e}", cause=e) from e
