"""Unit tests for Supabase-backed worker consumer."""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.queue.events import EventBus
from app.queue.worker import run_worker_loop
from app.services.supabase_queue_repository import QueueMessage


@pytest.fixture
def mock_queue_repo():
    repo = MagicMock()
    return repo


@pytest.fixture
def mock_run_repo():
    repo = MagicMock()
    repo.get_run_status.return_value = None  # not terminal
    return repo


@pytest.fixture
def mock_places_service():
    svc = MagicMock()
    svc.create_place_from_query.return_value = {"id": "page-123", "mode": "create"}
    return svc


@pytest.fixture
def event_bus():
    return EventBus()


def _valid_message():
    return QueueMessage(
        message_id=1,
        read_count=0,
        enqueued_at=datetime.now(),
        payload={
            "job_id": "loc_abc",
            "run_id": "run-xyz",
            "keywords": "coffee shop",
        },
    )


async def _run_worker_briefly(mock_queue_repo, mock_run_repo, mock_places_service, event_bus):
    """Run worker loop for ~0.5s then cancel."""
    task = asyncio.create_task(
        run_worker_loop(
            mock_queue_repo,
            mock_run_repo,
            mock_places_service,
            event_bus,
            poll_interval_seconds=0.1,
            vt_seconds=30,
        )
    )
    await asyncio.sleep(0.5)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def test_worker_success_path(
    mock_queue_repo, mock_run_repo, mock_places_service, event_bus
):
    """Success path: read -> persist running -> execute -> persist succeeded -> archive."""
    mock_queue_repo.read.side_effect = [
        [_valid_message()],
        [],
        [],
    ]

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_places_service, event_bus
    ))

    mock_run_repo.update_job_status.assert_called()
    calls = mock_run_repo.update_job_status.call_args_list
    assert any(c[0][1] == "running" for c in calls)
    assert any(c[0][1] == "succeeded" for c in calls)

    mock_run_repo.update_run.assert_called()
    mock_run_repo.insert_event.assert_called()
    event_types = [c[0][1] for c in mock_run_repo.insert_event.call_args_list]
    assert "pipeline_started" in event_types
    assert "pipeline_succeeded" in event_types

    mock_queue_repo.archive.assert_called_once_with(1)
    mock_places_service.create_place_from_query.assert_called_once_with("coffee shop")


def test_worker_failure_path(
    mock_queue_repo, mock_run_repo, mock_places_service, event_bus
):
    """Failure path: execute raises -> persist failed + event -> archive."""
    mock_queue_repo.read.side_effect = [
        [_valid_message()],
        [],
    ]
    mock_places_service.create_place_from_query.side_effect = ValueError("API error")

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_places_service, event_bus
    ))

    mock_run_repo.update_job_status.assert_called()
    calls = mock_run_repo.update_job_status.call_args_list
    assert any(c[0][1] == "running" for c in calls)
    assert any(c[0][1] == "failed" for c in calls)
    failed_call = next(c for c in calls if c[0][1] == "failed")
    assert failed_call[1].get("error_message") == "API error"

    mock_run_repo.insert_event.assert_called()
    event_calls = mock_run_repo.insert_event.call_args_list
    failed_event = next(c for c in event_calls if c[0][1] == "pipeline_failed")
    # Third positional arg is event_payload_json
    payload = failed_event[0][2] if len(failed_event[0]) > 2 else failed_event[1].get("event_payload_json", {})
    assert payload.get("error") == "API error"

    mock_queue_repo.archive.assert_called_once_with(1)


def test_worker_idempotency_skip(
    mock_queue_repo, mock_run_repo, mock_places_service, event_bus
):
    """Idempotency: terminal run status causes skip + archive, no pipeline execution."""
    mock_queue_repo.read.side_effect = [
        [_valid_message()],
        [],
    ]
    mock_run_repo.get_run_status.return_value = "succeeded"

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_places_service, event_bus
    ))

    mock_run_repo.update_job_status.assert_not_called()
    mock_run_repo.update_run.assert_not_called()
    mock_run_repo.insert_event.assert_not_called()
    mock_places_service.create_place_from_query.assert_not_called()
    mock_queue_repo.archive.assert_called_once_with(1)


def test_worker_malformed_payload_archives(
    mock_queue_repo, mock_run_repo, mock_places_service, event_bus
):
    """Malformed payload: archive without executing, no persistence."""
    malformed = QueueMessage(
        message_id=2,
        read_count=0,
        enqueued_at=datetime.now(),
        payload={"job_id": "loc_x"},  # missing run_id, keywords
    )
    mock_queue_repo.read.side_effect = [
        [malformed],
        [],
    ]

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_places_service, event_bus
    ))

    mock_run_repo.update_job_status.assert_not_called()
    mock_run_repo.update_run.assert_not_called()
    mock_run_repo.insert_event.assert_not_called()
    mock_places_service.create_place_from_query.assert_not_called()
    mock_queue_repo.archive.assert_called_once_with(2)
