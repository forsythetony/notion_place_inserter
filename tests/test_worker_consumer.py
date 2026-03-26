"""Unit tests for Supabase-backed worker consumer."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.queue.events import EventBus
from app.queue.worker import _extract_notion_data_source_id_from_error, run_worker_loop
from app.services.supabase_queue_repository import QueueMessage


@pytest.fixture
def mock_queue_repo():
    repo = MagicMock()
    repo.read = AsyncMock(return_value=[])
    repo.archive = AsyncMock()
    return repo


@pytest.fixture
def mock_run_repo():
    repo = MagicMock()
    repo.get_run_status = AsyncMock(return_value=None)  # not terminal
    repo.get_job_retry_count = AsyncMock(return_value=0)
    repo.update_job_status = AsyncMock()
    repo.update_run = AsyncMock()
    repo.insert_event = AsyncMock()
    repo.increment_job_retry_count = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_job_definition_service():
    svc = MagicMock()
    snapshot = MagicMock()
    snapshot.snapshot = {"job": {}, "target": {"external_target_id": "ds-123"}, "active_schema": {}}
    snapshot.snapshot_ref = "job_snapshot:user1:job1:abc"
    svc.resolve_for_run = AsyncMock(return_value=snapshot)
    return svc


@pytest.fixture
def mock_job_execution_service():
    svc = MagicMock()
    svc.execute_snapshot_run = AsyncMock(
        return_value={"id": "page-123", "mode": "create"}
    )
    return svc


@pytest.fixture
def event_bus():
    return EventBus()


def _valid_message(job_definition_id="job_notion_place_inserter", job_slug=None, owner_user_id="user_test", trigger_id="trigger_http_locations"):
    payload = {
        "job_id": "loc_abc",
        "run_id": "run-xyz",
        "keywords": "coffee shop",
        "job_definition_id": job_definition_id,
        "trigger_id": trigger_id,
        "owner_user_id": owner_user_id,
    }
    if job_slug is not None:
        payload["job_slug"] = job_slug
    payload["definition_snapshot_ref"] = "job_snapshot:user_test:job1:abc"
    return QueueMessage(
        message_id=1,
        read_count=0,
        enqueued_at=datetime.now(),
        payload=payload,
    )


async def _run_worker_briefly(
    mock_queue_repo,
    mock_run_repo,
    mock_job_execution_service,
    mock_job_definition_service,
    event_bus,
    *,
    retry_delays_seconds=(0.01, 0.02, 0.03),
):
    """Run worker loop for ~0.5s then cancel. Short retry delays for fast tests."""
    task = asyncio.create_task(
        run_worker_loop(
            mock_queue_repo,
            mock_run_repo,
            mock_job_execution_service,
            mock_job_definition_service,
            event_bus,
            poll_interval_seconds=0.1,
            vt_seconds=30,
            retry_delays_seconds=retry_delays_seconds,
        )
    )
    await asyncio.sleep(0.5)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def test_worker_success_path(
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
):
    """Success path: read -> persist running -> execute -> persist succeeded -> archive."""
    mock_queue_repo.read.side_effect = [
        [_valid_message()],
        [],
        [],
    ]

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
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
    mock_job_execution_service.execute_snapshot_run.assert_called_once()


def test_worker_pipeline_started_includes_job_definition_metadata(
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
):
    """When payload has job_definition_id and job_slug, pipeline_started event includes them."""
    mock_queue_repo.read.side_effect = [
        [_valid_message(job_definition_id="job_notion_place_inserter", job_slug="notion_place_inserter")],
        [],
        [],
    ]

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
    ))

    pipeline_started_calls = [
        c for c in mock_run_repo.insert_event.call_args_list
        if c[0][1] == "pipeline_started"
    ]
    assert len(pipeline_started_calls) == 1
    event_payload = pipeline_started_calls[0][0][2]
    assert event_payload.get("job_definition_id") == "job_notion_place_inserter"
    assert event_payload.get("job_slug") == "notion_place_inserter"


def test_worker_failure_path(
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
):
    """Failure path: execute raises -> persist failed + event -> archive."""
    mock_queue_repo.read.side_effect = [
        [_valid_message()],
        [],
    ]
    mock_job_execution_service.execute_snapshot_run.side_effect = ValueError("API error")

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
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
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
):
    """Idempotency: terminal run status causes skip + archive, no pipeline execution."""
    mock_queue_repo.read.side_effect = [
        [_valid_message()],
        [],
    ]
    mock_run_repo.get_run_status.return_value = "succeeded"

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
    ))

    mock_run_repo.update_job_status.assert_not_called()
    mock_run_repo.update_run.assert_not_called()
    mock_run_repo.insert_event.assert_not_called()
    mock_job_execution_service.execute_snapshot_run.assert_not_called()
    mock_queue_repo.archive.assert_called_once_with(1)


def test_worker_malformed_payload_archives(
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
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
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
    ))

    mock_run_repo.update_job_status.assert_not_called()
    mock_run_repo.update_run.assert_not_called()
    mock_run_repo.insert_event.assert_not_called()
    mock_job_execution_service.execute_snapshot_run.assert_not_called()
    mock_queue_repo.archive.assert_called_once_with(2)


def test_worker_idempotency_skip_failed_run(
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
):
    """Idempotency: run already failed causes skip + archive, no pipeline execution."""
    mock_queue_repo.read.side_effect = [
        [_valid_message()],
        [],
    ]
    mock_run_repo.get_run_status.return_value = "failed"

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
    ))

    mock_run_repo.update_job_status.assert_not_called()
    mock_run_repo.update_run.assert_not_called()
    mock_run_repo.insert_event.assert_not_called()
    mock_job_execution_service.execute_snapshot_run.assert_not_called()
    mock_queue_repo.archive.assert_called_once_with(1)


def test_worker_queue_read_error_continues(
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
):
    """Queue read exception: worker logs, sleeps, and continues without crashing."""
    mock_queue_repo.read.side_effect = [
        RuntimeError("pgmq_read failed"),
        [],
        [],
    ]

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
    ))

    # Worker should have called read multiple times (retries after error)
    assert mock_queue_repo.read.call_count >= 2
    mock_queue_repo.archive.assert_not_called()


def test_worker_persist_running_failed_retries_then_archives(
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
):
    """When persist-running fails, worker retries with backoff then marks failed and archives."""
    mock_queue_repo.read.side_effect = [
        [_valid_message()],
        [],
    ]
    mock_run_repo.update_job_status.side_effect = RuntimeError("DB write failed")

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
    ))

    mock_queue_repo.archive.assert_called_once_with(1)
    mock_job_execution_service.execute_snapshot_run.assert_not_called()
    mock_run_repo.increment_job_retry_count.assert_called()


def test_worker_persist_failure_failed_archives_via_handler(
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
):
    """When pipeline fails but persist-failure raises, outer handler archives to avoid poison loop."""
    mock_queue_repo.read.side_effect = [
        [_valid_message()],
        [],
    ]
    mock_job_execution_service.execute_snapshot_run.side_effect = ValueError("API error")
    # update_job_status for "running" succeeds; for "failed" we make it raise
    def update_job_status_side_effect(job_id, status, **kw):
        if status == "failed":
            raise RuntimeError("persist failed")

    mock_run_repo.update_job_status.side_effect = update_job_status_side_effect

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
    ))

    mock_queue_repo.archive.assert_called_once_with(1)


def test_worker_persist_success_failed_retries_then_archives(
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
):
    """When pipeline succeeds but persist-success raises, worker retries then marks failed and archives."""
    mock_queue_repo.read.side_effect = [
        [_valid_message()],
        [],
    ]

    def update_job_status_side_effect(job_id, status, **kw):
        if status == "succeeded":
            raise RuntimeError("persist success failed")

    mock_run_repo.update_job_status.side_effect = update_job_status_side_effect

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
    ))

    mock_queue_repo.archive.assert_called_once_with(1)
    mock_run_repo.increment_job_retry_count.assert_called()


def test_worker_retry_then_succeeds(
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
):
    """Pipeline fails twice then succeeds on third attempt; message archived."""
    mock_queue_repo.read.side_effect = [
        [_valid_message()],
        [],
    ]
    mock_job_execution_service.execute_snapshot_run.side_effect = [
        ValueError("API error 1"),
        ValueError("API error 2"),
        {"id": "page-123", "mode": "create"},
    ]

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
    ))

    mock_queue_repo.archive.assert_called_once_with(1)
    mock_run_repo.increment_job_retry_count.assert_called()
    calls = mock_run_repo.increment_job_retry_count.call_args_list
    assert len(calls) == 2  # after first and second failure
    assert calls[0][0][1] == 1
    assert calls[1][0][1] == 2
    status_calls = [c[0][1] for c in mock_run_repo.update_job_status.call_args_list]
    assert "succeeded" in status_calls


def test_worker_retry_exhausted_marks_failed_and_archives(
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
):
    """Pipeline fails all attempts; worker marks failed and archives after final attempt."""
    mock_queue_repo.read.side_effect = [
        [_valid_message()],
        [],
    ]
    mock_job_execution_service.execute_snapshot_run.side_effect = ValueError("API error")

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
    ))

    mock_queue_repo.archive.assert_called_once_with(1)
    status_calls = [c[0][1] for c in mock_run_repo.update_job_status.call_args_list]
    assert "failed" in status_calls


def test_worker_non_retriable_fk_violation_archives_immediately(
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
):
    """When persist-running fails with FK violation (23503), worker archives immediately without retry."""
    mock_queue_repo.read.side_effect = [
        [_valid_message()],
        [],
    ]

    class APIErrorWithCode(Exception):
        def __init__(self, code: str, message: str):
            super().__init__(message)
            self.code = code

    def insert_event_raises_fk(*args, **kwargs):
        raise APIErrorWithCode(
            "23503",
            "insert or update on table pipeline_run_events violates foreign key constraint",
        )

    mock_run_repo.insert_event.side_effect = insert_event_raises_fk

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
    ))

    mock_queue_repo.archive.assert_called_once_with(1)
    mock_job_execution_service.execute_snapshot_run.assert_not_called()
    mock_run_repo.increment_job_retry_count.assert_not_called()
    status_calls = [c[0][1] for c in mock_run_repo.update_job_status.call_args_list]
    assert "failed" in status_calls


def test_worker_non_retriable_terminal_persist_failure_still_archives_once(
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
):
    """Non-retriable FK should still archive even if pipeline_failed event persist also fails."""
    mock_queue_repo.read.side_effect = [
        [_valid_message()],
        [],
    ]

    class APIErrorWithCode(Exception):
        def __init__(self, code: str, message: str):
            super().__init__(message)
            self.code = code

    call_count = {"n": 0}

    def insert_event_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise APIErrorWithCode("23503", "fk violation pipeline_started")
        if call_count["n"] == 2:
            raise APIErrorWithCode("23503", "fk violation pipeline_failed")
        return None

    mock_run_repo.insert_event.side_effect = insert_event_side_effect

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
    ))

    mock_queue_repo.archive.assert_called_once_with(1)
    failed_status_calls = [
        c for c in mock_run_repo.update_job_status.call_args_list if c[0][1] == "failed"
    ]
    assert len(failed_status_calls) == 1
    mock_run_repo.increment_job_retry_count.assert_not_called()


def test_worker_read_count_ceiling_forces_terminal(
    mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
):
    """When message read_count exceeds ceiling, worker forces terminal without retry."""
    high_read_count_msg = QueueMessage(
        message_id=3,
        read_count=25,
        enqueued_at=datetime.now(),
        payload={
            "job_id": "loc_abc",
            "run_id": "run-xyz",
            "keywords": "coffee shop",
            "job_definition_id": "job1",
            "owner_user_id": "user1",
        },
    )
    mock_queue_repo.read.side_effect = [
        [high_read_count_msg],
        [],
    ]

    asyncio.run(_run_worker_briefly(
        mock_queue_repo, mock_run_repo, mock_job_execution_service, mock_job_definition_service, event_bus
    ))

    mock_queue_repo.archive.assert_called_once_with(3)
    mock_job_execution_service.execute_snapshot_run.assert_not_called()
    event_types = [c[0][1] for c in mock_run_repo.insert_event.call_args_list]
    assert "pipeline_started" not in event_types
    assert "pipeline_failed" in event_types
    status_calls = [c[0][1] for c in mock_run_repo.update_job_status.call_args_list]
    assert "failed" in status_calls


def test_extract_notion_data_source_id_from_error():
    """_extract_notion_data_source_id_from_error extracts UUID from data_source error messages."""
    err_msg = "Could not find data_source with ID: 1e2a5cd4-f107-490f-9b7a-4af865fd1beb. Make sure..."
    assert _extract_notion_data_source_id_from_error(ValueError(err_msg)) == "1e2a5cd4-f107-490f-9b7a-4af865fd1beb"

    assert _extract_notion_data_source_id_from_error(ValueError("Some other error")) is None
    assert _extract_notion_data_source_id_from_error(ValueError("data_source foo bar")) is None
    assert _extract_notion_data_source_id_from_error(ValueError("data_source id: abc-def-123")) is None
