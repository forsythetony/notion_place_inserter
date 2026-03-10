"""Orchestration layer for user-facing run-status notifications over WhatsApp."""

import re

from loguru import logger

from app.queue.models import PipelineFailureEvent, PipelineSuccessEvent
from app.services.whatsapp_service import WhatsAppService, WhatsAppServiceError


def _sanitize_error(text: str) -> str:
    """Redact common secret patterns from error text."""
    # Redact Notion, Anthropic, Twilio, and generic API key patterns
    patterns = [
        (r"secret_[a-zA-Z0-9]+", "secret_***"),
        (r"sk-ant-[a-zA-Z0-9-]+", "sk-ant-***"),
        (r"sk-[a-zA-Z0-9]+", "sk-***"),
        (r"AIza[a-zA-Z0-9_-]+", "AIza***"),
        (r"fpk_[a-zA-Z0-9]+", "fpk_***"),
    ]
    out = text
    for pat, repl in patterns:
        out = re.sub(pat, repl, out)
    return out


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text and append ... if needed."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


class Communicator:
    """
    Primary orchestration layer for user-facing notifications.
    Accepts domain events, builds concise messages, applies policy,
    and delegates transport to WhatsAppService.
    """

    def __init__(
        self,
        whatsapp_service: WhatsAppService,
        *,
        enabled: bool = True,
        default_recipient: str | None = None,
        max_error_chars: int = 300,
    ) -> None:
        self._whatsapp = whatsapp_service
        self._enabled = enabled
        self._default_recipient = default_recipient
        self._max_error_chars = max_error_chars

    def notify_pipeline_success(self, event: PipelineSuccessEvent) -> None:
        """Send success notification with Notion page link when recipient available."""
        recipient = event.recipient_whatsapp or self._default_recipient
        if not recipient:
            logger.warning("notification_skipped_no_recipient", job_id=event.job_id)
            return
        if not self._enabled:
            logger.debug("notification_skipped_disabled", job_id=event.job_id)
            return

        url = event.result.get("url") if isinstance(event.result, dict) else None
        link = url if url else "(page created)"
        body = f'Done: created your place page for "{event.keywords}". {link}'

        try:
            self._whatsapp.send_message(to_number=recipient, body=body)
        except WhatsAppServiceError as e:
            logger.warning(
                "communicator_send_failed",
                job_id=event.job_id,
                error=str(e),
            )

    def notify_pipeline_failure(self, event: PipelineFailureEvent) -> None:
        """Send failure notification with truncated, sanitized error when recipient available."""
        recipient = event.recipient_whatsapp or self._default_recipient
        if not recipient:
            logger.warning("notification_skipped_no_recipient", job_id=event.job_id)
            return
        if not self._enabled:
            logger.debug("notification_skipped_disabled", job_id=event.job_id)
            return

        err_text = str(event.error) if isinstance(event.error, Exception) else event.error
        err_text = _sanitize_error(err_text)
        err_text = _truncate(err_text, self._max_error_chars)
        body = f'Could not create a page for "{event.keywords}". Error: {err_text}.'

        try:
            self._whatsapp.send_message(to_number=recipient, body=body)
        except WhatsAppServiceError as e:
            logger.warning(
                "communicator_send_failed",
                job_id=event.job_id,
                error=str(e),
            )
