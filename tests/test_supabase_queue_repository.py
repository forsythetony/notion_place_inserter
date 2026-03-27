"""Unit tests for Supabase queue repository (with mocks)."""

from unittest.mock import AsyncMock, MagicMock

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
        table_beta_waitlist_submissions="beta_waitlist_submissions",
        table_beta_waves="beta_waves",
    )


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def repo(mock_client, config):
    return SupabaseQueueRepository(mock_client, config)


async def test_send_returns_message_id(repo, mock_client):
    """Send calls public.pgmq_send RPC and returns normalized QueueSendResult."""
    mock_client.rpc.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[42])
    )
    result = await repo.send({"job_id": "loc_abc", "keywords": "coffee"})
    assert result == QueueSendResult(message_id=42)
    mock_client.rpc.assert_called_once_with(
        "pgmq_send",
        {
            "queue_name": "locations_jobs",
            "msg": {"job_id": "loc_abc", "keywords": "coffee"},
            "delay": 0,
        },
    )


async def test_read_returns_normalized_messages(repo, mock_client):
    """Read calls public.pgmq_read RPC and returns list of QueueMessage."""
    mock_client.rpc.return_value.execute = AsyncMock(
        return_value=MagicMock(
            data=[
                {
                    "msg_id": 1,
                    "read_ct": 1,
                    "enqueued_at": "2024-01-15T10:00:00Z",
                    "message": {"job_id": "loc_1", "keywords": "park"},
                }
            ]
        )
    )
    messages = await repo.read(batch_size=1, vt_seconds=30)
    assert len(messages) == 1
    assert messages[0].message_id == 1
    assert messages[0].read_count == 1
    assert messages[0].payload == {"job_id": "loc_1", "keywords": "park"}
    mock_client.rpc.assert_called_once_with(
        "pgmq_read",
        {"queue_name": "locations_jobs", "vt": 30, "qty": 1},
    )


async def test_read_empty_returns_empty_list(repo, mock_client):
    """Read with no messages returns empty list."""
    mock_client.rpc.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[])
    )
    messages = await repo.read(batch_size=5, vt_seconds=10)
    assert messages == []


async def test_archive_calls_rpc_and_returns_result(repo, mock_client):
    """Archive calls public.pgmq_archive RPC and returns QueueAckResult."""
    mock_client.rpc.return_value.execute = AsyncMock(
        return_value=MagicMock(data=True)
    )
    result = await repo.archive(message_id=99)
    assert result == QueueAckResult(archived=True)
    mock_client.rpc.assert_called_once_with(
        "pgmq_archive",
        {"queue_name": "locations_jobs", "msg_id": 99},
    )


async def test_aclose_invokes_postgrest_aclose(repo, mock_client):
    """aclose() awaits PostgREST session shutdown when present."""
    mock_pg = MagicMock()
    mock_pg.aclose = AsyncMock()
    mock_client._postgrest = mock_pg
    await repo.aclose()
    mock_pg.aclose.assert_awaited_once()


async def test_aclose_idempotent(repo, mock_client):
    """aclose() is safe to call multiple times."""
    mock_pg = MagicMock()
    mock_pg.aclose = AsyncMock()
    mock_client._postgrest = mock_pg
    await repo.aclose()
    await repo.aclose()
    assert mock_pg.aclose.await_count == 2


async def test_aclose_no_postgrest_does_not_raise(repo, mock_client):
    """aclose() does not raise when client has no _postgrest."""
    mock_client._postgrest = None
    await repo.aclose()


async def test_aclose_postgrest_error_logged_does_not_raise(repo, mock_client):
    """aclose() logs but does not raise when aclose() raises."""
    mock_pg = MagicMock()
    mock_pg.aclose = AsyncMock(side_effect=RuntimeError("connection reset"))
    mock_client._postgrest = mock_pg
    await repo.aclose()


def test_sync_close_is_noop(repo, mock_client):
    """Sync close() is a no-op and must not raise (prefer ``await aclose()``)."""
    repo.close()
