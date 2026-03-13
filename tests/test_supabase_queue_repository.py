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
    )


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def repo(mock_client, config):
    return SupabaseQueueRepository(mock_client, config)


def test_send_returns_message_id(repo, mock_client):
    """Send calls pgmq.send RPC and returns normalized QueueSendResult."""
    mock_client.schema.return_value.rpc.return_value.execute.return_value = MagicMock(
        data=[42]
    )
    result = repo.send({"job_id": "loc_abc", "keywords": "coffee"})
    assert result == QueueSendResult(message_id=42)
    mock_client.schema.assert_called_with("pgmq")
    mock_client.schema.return_value.rpc.assert_called_once()
    call_args = mock_client.schema.return_value.rpc.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params["queue_name"] == "locations_jobs"
    assert params["msg"] == {"job_id": "loc_abc", "keywords": "coffee"}
    assert params["delay"] == 0


def test_read_returns_normalized_messages(repo, mock_client):
    """Read calls pgmq.read RPC and returns list of QueueMessage."""
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
    call_args = mock_client.schema.return_value.rpc.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params["queue_name"] == "locations_jobs"
    assert params["vt"] == 30
    assert params["qty"] == 1


def test_read_empty_returns_empty_list(repo, mock_client):
    """Read with no messages returns empty list."""
    mock_client.schema.return_value.rpc.return_value.execute.return_value = MagicMock(
        data=[]
    )
    messages = repo.read(batch_size=5, vt_seconds=10)
    assert messages == []


def test_archive_calls_rpc_and_returns_result(repo, mock_client):
    """Archive calls pgmq.archive RPC and returns QueueAckResult."""
    mock_client.schema.return_value.rpc.return_value.execute.return_value = MagicMock(
        data=True
    )
    result = repo.archive(message_id=99)
    assert result == QueueAckResult(archived=True)
    call_args = mock_client.schema.return_value.rpc.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params["queue_name"] == "locations_jobs"
    assert params["msg_id"] == 99
