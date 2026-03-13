"""Unit tests for queue event bus and success subscriber."""

from app.queue.events import EventBus, subscribe_to_success
from app.queue.models import PipelineSuccessEvent


def test_subscriber_logs_success():
    """Success subscriber is invoked and logs 'Pipeline executed successfully!'."""
    logged: list[str] = []

    def capture_log(event: PipelineSuccessEvent) -> None:
        logged.append("Pipeline executed successfully!")

    bus = EventBus()
    bus.subscribe_success(capture_log)

    event = PipelineSuccessEvent(
        job_id="loc_abc123",
        run_id="run-456",
        keywords="test place",
        result={"id": "page-1"},
    )
    bus.publish_success(event)

    assert logged == ["Pipeline executed successfully!"]


def test_subscribe_to_success_registers_default_handler():
    """subscribe_to_success registers the default handler that logs the message."""
    bus = EventBus()
    subscribe_to_success(bus)
    # Publish should not raise; default handler logs
    bus.publish_success(
        PipelineSuccessEvent(
            job_id="loc_x",
            run_id="run_y",
            keywords="k",
            result={},
        )
    )
