"""Unit tests for id_mapping registry (first-write, reuse, mismatch, FK chain)."""

from unittest.mock import MagicMock

import pytest

from app.repositories.id_mapping import resolve_or_create_mapping, verify_mapping_consistency


@pytest.fixture
def mock_client():
    return MagicMock()


def test_resolve_or_create_mapping_first_write_inserts(mock_client):
    """First write: lookup returns empty, compute UUID, insert mapping."""
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock()
    result = resolve_or_create_mapping(mock_client, "stage_run", "stage_1_run_xyz")
    assert result is not None
    mock_client.table.assert_any_call("id_mappings")
    insert_call = mock_client.table.return_value.insert.call_args[0][0]
    assert insert_call["entity_type"] == "stage_run"
    assert insert_call["source_id"] == "stage_1_run_xyz"
    assert "mapped_uuid" in insert_call


def test_resolve_or_create_mapping_reuse_existing(mock_client):
    """Repeated write: lookup returns stored mapping, reuse it (no insert)."""
    from uuid import uuid4
    stored_uuid = str(uuid4())
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"mapped_uuid": stored_uuid}]
    )
    result = resolve_or_create_mapping(mock_client, "stage_run", "stage_1_run_xyz")
    assert str(result) == stored_uuid
    mock_client.table.return_value.insert.assert_not_called()


def test_resolve_or_create_mapping_race_retry_lookup(mock_client):
    """Insert fails (race); retry lookup returns existing mapping."""
    from uuid import uuid4
    stored_uuid = str(uuid4())
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.side_effect = [
        MagicMock(data=[]),
        MagicMock(data=[{"mapped_uuid": stored_uuid}]),
    ]
    mock_client.table.return_value.insert.return_value.execute.side_effect = Exception("unique violation")
    result = resolve_or_create_mapping(mock_client, "stage_run", "stage_1_run_xyz")
    assert str(result) == stored_uuid


def test_verify_mapping_consistency_passes_when_empty(mock_client):
    """verify_mapping_consistency passes when no rows to verify."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    verify_mapping_consistency(mock_client, sample_size=5)


def test_verify_mapping_consistency_raises_on_mismatch(mock_client):
    """verify_mapping_consistency raises RuntimeError when stored != computed."""
    wrong_uuid = "00000000-0000-0000-0000-000000000001"
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[
            {
                "entity_type": "stage_run",
                "source_id": "test_source_123",
                "mapped_uuid": wrong_uuid,
            }
        ]
    )
    with pytest.raises(RuntimeError, match="id_mapping_mismatch"):
        verify_mapping_consistency(mock_client, sample_size=5)
