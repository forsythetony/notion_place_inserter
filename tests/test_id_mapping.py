"""Unit tests for id_mapping registry (first-write, reuse, mismatch, FK chain)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.id_mapping import resolve_or_create_mapping, verify_mapping_consistency


@pytest.fixture
def mock_client():
    return MagicMock()


def test_resolve_or_create_mapping_first_write_inserts(mock_client):
    """First write: lookup returns empty, compute UUID, insert mapping."""
    tbl = mock_client.table.return_value
    lookup_exec = AsyncMock(return_value=MagicMock(data=[]))
    tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute = (
        lookup_exec
    )
    insert_exec = AsyncMock(return_value=MagicMock())
    tbl.insert.return_value.execute = insert_exec

    result = asyncio.run(
        resolve_or_create_mapping(mock_client, "stage_run", "stage_1_run_xyz")
    )
    assert result is not None
    mock_client.table.assert_any_call("id_mappings")
    insert_call = tbl.insert.call_args[0][0]
    assert insert_call["entity_type"] == "stage_run"
    assert insert_call["source_id"] == "stage_1_run_xyz"
    assert "mapped_uuid" in insert_call


def test_resolve_or_create_mapping_reuse_existing(mock_client):
    """Repeated write: lookup returns stored mapping, reuse it (no insert)."""
    from uuid import uuid4

    stored_uuid = str(uuid4())
    tbl = mock_client.table.return_value
    tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute = (
        AsyncMock(return_value=MagicMock(data=[{"mapped_uuid": stored_uuid}]))
    )

    result = asyncio.run(
        resolve_or_create_mapping(mock_client, "stage_run", "stage_1_run_xyz")
    )
    assert str(result) == stored_uuid
    tbl.insert.assert_not_called()


def test_resolve_or_create_mapping_race_retry_lookup(mock_client):
    """Insert fails (race); retry lookup returns existing mapping."""
    from uuid import uuid4

    stored_uuid = str(uuid4())
    tbl = mock_client.table.return_value
    tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute = (
        AsyncMock(
            side_effect=[
                MagicMock(data=[]),
                MagicMock(data=[{"mapped_uuid": stored_uuid}]),
            ]
        )
    )
    tbl.insert.return_value.execute = AsyncMock(
        side_effect=Exception("unique violation")
    )

    result = asyncio.run(
        resolve_or_create_mapping(mock_client, "stage_run", "stage_1_run_xyz")
    )
    assert str(result) == stored_uuid


def test_verify_mapping_consistency_passes_when_empty(mock_client):
    """verify_mapping_consistency passes when no rows to verify."""
    exec_mock = AsyncMock(return_value=MagicMock(data=[]))
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute = exec_mock
    asyncio.run(verify_mapping_consistency(mock_client, sample_size=5))


def test_verify_mapping_consistency_raises_on_mismatch(mock_client):
    """verify_mapping_consistency raises RuntimeError when stored != computed."""
    wrong_uuid = "00000000-0000-0000-0000-000000000001"
    exec_mock = AsyncMock(
        return_value=MagicMock(
            data=[
                {
                    "entity_type": "stage_run",
                    "source_id": "test_source_123",
                    "mapped_uuid": wrong_uuid,
                }
            ]
        )
    )
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute = exec_mock
    with pytest.raises(RuntimeError, match="id_mapping_mismatch"):
        asyncio.run(verify_mapping_consistency(mock_client, sample_size=5))
