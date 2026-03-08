"""In-memory event bus and subscribers for pipeline outcomes."""

from collections.abc import Callable
from typing import Any

from loguru import logger

from app.queue.models import PipelineFailureEvent, PipelineSuccessEvent


class EventBus:
    """Simple in-memory event bus for pipeline success/failure signals."""

    def __init__(self) -> None:
        self._success_handlers: list[Callable[[PipelineSuccessEvent], None]] = []
        self._failure_handlers: list[Callable[[PipelineFailureEvent], None]] = []

    def subscribe_success(self, handler: Callable[[PipelineSuccessEvent], None]) -> None:
        """Register a handler for success events."""
        self._success_handlers.append(handler)

    def subscribe_failure(self, handler: Callable[[PipelineFailureEvent], None]) -> None:
        """Register a handler for failure events."""
        self._failure_handlers.append(handler)

    def publish_success(self, event: PipelineSuccessEvent) -> None:
        """Notify all success subscribers."""
        for h in self._success_handlers:
            try:
                h(event)
            except Exception as e:
                logger.exception("Success subscriber error: {}", e)

    def publish_failure(self, event: PipelineFailureEvent) -> None:
        """Notify all failure subscribers."""
        for h in self._failure_handlers:
            try:
                h(event)
            except Exception as e:
                logger.exception("Failure subscriber error: {}", e)


def _on_success(_event: PipelineSuccessEvent) -> None:
    """Default success subscriber: log exactly as specified."""
    logger.info("Pipeline executed successfully!")


def _on_failure(event: PipelineFailureEvent) -> None:
    """Default failure subscriber: structured error logging."""
    err = str(event.error) if isinstance(event.error, Exception) else event.error
    logger.error(
        "Pipeline failed",
        job_id=event.job_id,
        run_id=event.run_id,
        keywords=event.keywords[:50],
        error=err,
    )


def subscribe_to_success(bus: EventBus) -> None:
    """Register the success subscriber that logs 'Pipeline executed successfully!'."""
    bus.subscribe_success(_on_success)
    bus.subscribe_failure(_on_failure)
