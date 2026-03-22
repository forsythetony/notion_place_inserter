"""Unit tests for Supabase queue repository (with mocks)."""

from unittest.mock import MagicMock

import pytest

from app.integrations.supabase_config import SupabaseConfig
from app.services.supabase_queue_repository import (
    QueueAckResult,
    QueueMessage,
    QueueSendResult,
    SupabaseQueueRepository,
)


@pytest.fixture
def config():
    return SupabaseConfig(
        url="https://test.supabase.co",
        secret_key="test-key",
        queue_name="locations_jobs",
        table_platform_jobs="platform_jobs",
        table_pipeline_runs="pipeline_runs",
        table_pipeline_run_events="pipeline_run_events",
        table_user_profiles="user_profiles",
        table_invitation_codes="invitation_codes",
        table_user_cohorts="user_cohorts",
    )


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def repo(mock_client, config):
    return SupabaseQueueRepository(mock_client, config)


def test_send_returns_message_id(repo, mock_client):
    """Send calls public.pgmq_send RPC and returns normalized QueueSendResult."""
    mock_client.schema.return_value.rpc.return_value.execute.return_value = MagicMock(
        data=[42]
    )
    result = repo.send({"job_id": "loc_abc", "keywords": "coffee"})
    assert result == QueueSendResult(message_id=42)
    mock_client.schema.assert_called_once_with("public")
    mock_client.schema.return_value.rpc.assert_called_once_with(
        "pgmq_send",
        {"queue_name": "locations_jobs", "msg": {"job_id": "loc_abc", "keywords": "coffee"}, "delay": 0},
    )


def test_read_returns_normalized_messages(repo, mock_client):
    """Read calls public.pgmq_read RPC and returns list of QueueMessage."""
    mock_client.schema.return_value.rpc.return_value.execute.return_value = MagicMock(
        data=[
            {
                "msg_id": 1,
                "read_ct": 1,
                "enqueued_at": "2024-01-15T10:00:00Z",
                "message": {"job_id": "loc_1", "keywords": "park"},
            }
        ]
    )
    messages = repo.read(batch_size=1, vt_seconds=30)
    assert len(messages) == 1
    assert messages[0].message_id == 1
    assert messages[0].read_count == 1
    assert messages[0].payload == {"job_id": "loc_1", "keywords": "park"}
    mock_client.schema.assert_called_once_with("public")
    mock_client.schema.return_value.rpc.assert_called_once_with(
        "pgmq_read",
        {"queue_name": "locations_jobs", "vt": 30, "qty": 1},
    )


def test_read_empty_returns_empty_list(repo, mock_client):
    """Read with no messages returns empty list."""
    mock_client.schema.return_value.rpc.return_value.execute.return_value = MagicMock(
        data=[]
    )
    messages = repo.read(batch_size=5, vt_seconds=10)
    assert messages == []


def test_archive_calls_rpc_and_returns_result(repo, mock_client):
    """Archive calls public.pgmq_archive RPC and returns QueueAckResult."""
    mock_client.schema.return_value.rpc.return_value.execute.return_value = MagicMock(
        data=True
    )
    result = repo.archive(message_id=99)
    assert result == QueueAckResult(archived=True)
    mock_client.schema.assert_called_once_with("public")
    mock_client.schema.return_value.rpc.assert_called_once_with(
        "pgmq_archive",
        {"queue_name": "locations_jobs", "msg_id": 99},
    )


def test_close_invokes_session_close(repo, mock_client):
    """close() calls session.close() when schema client has a session."""
    mock_session = MagicMock()
    mock_client.schema.return_value.session = mock_session
    repo.close()
    mock_session.close.assert_called_once()


def test_close_idempotent(repo, mock_client):
    """close() is safe to call multiple times."""
    mock_session = MagicMock()
    mock_client.schema.return_value.session = mock_session
    repo.close()
    repo.close()
    mock_session.close.assert_called()


def test_close_no_session_does_not_raise(repo, mock_client):
    """close() does not raise when schema client has no session."""
    mock_client.schema.return_value.session = None
    repo.close()  # no raise


def test_close_session_error_logged_does_not_raise(repo, mock_client):
    """close() logs but does not raise when session.close() raises."""
    mock_session = MagicMock()
    mock_session.close.side_effect = RuntimeError("connection reset")
    mock_client.schema.return_value.session = mock_session
    repo.close()  # no raise
