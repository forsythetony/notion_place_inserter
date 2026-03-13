"""Unit tests for Supabase run repository (with mocks)."""

from unittest.mock import MagicMock

import pytest

from app.integrations.supabase_config import SupabaseConfig
from app.services.supabase_run_repository import SupabaseRunRepository


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
    return SupabaseRunRepository(mock_client, config)


def test_create_job_inserts_into_platform_jobs(repo, mock_client):
    """Create job inserts row with job_id, keywords, status."""
    repo.create_job(job_id="loc_abc", keywords="coffee shop")
    mock_client.table.assert_called_with("platform_jobs")
    mock_client.table.return_value.insert.assert_called_once()
    call_arg = mock_client.table.return_value.insert.call_args[0][0]
    assert call_arg["job_id"] == "loc_abc"
    assert call_arg["keywords"] == "coffee shop"
    assert call_arg["status"] == "queued"


def test_update_job_status_updates_row(repo, mock_client):
    """Update job status patches platform_jobs by job_id."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    repo.update_job_status(
        job_id="loc_xyz",
        status="completed",
        completed_at=now,
        error_message=None,
    )
    mock_client.table.assert_called_with("platform_jobs")
    mock_client.table.return_value.update.assert_called_once()
    call_arg = mock_client.table.return_value.update.call_args[0][0]
    assert call_arg["status"] == "completed"
    assert "completed_at" in call_arg
    mock_client.table.return_value.update.return_value.eq.assert_called_with(
        "job_id", "loc_xyz"
    )


def test_create_run_inserts_into_pipeline_runs(repo, mock_client):
    """Create run inserts row with job_id, run_id, status."""
    repo.create_run(job_id="loc_1", run_id="run_abc", status="pending")
    mock_client.table.assert_called_with("pipeline_runs")
    call_arg = mock_client.table.return_value.insert.call_args[0][0]
    assert call_arg["job_id"] == "loc_1"
    assert call_arg["run_id"] == "run_abc"
    assert call_arg["status"] == "pending"


def test_update_run_patches_by_run_id(repo, mock_client):
    """Update run patches pipeline_runs by run_id."""
    repo.update_run(
        run_id="run_xyz",
        status="completed",
        result_json={"page_id": "abc"},
    )
    mock_client.table.assert_called_with("pipeline_runs")
    call_arg = mock_client.table.return_value.update.call_args[0][0]
    assert call_arg["status"] == "completed"
    assert call_arg["result_json"] == {"page_id": "abc"}
    mock_client.table.return_value.update.return_value.eq.assert_called_with(
        "run_id", "run_xyz"
    )


def test_get_run_status_returns_status_when_found(repo, mock_client):
    """get_run_status returns status when run exists."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"status": "succeeded"}]
    )
    status = repo.get_run_status("run_xyz")
    assert status == "succeeded"
    mock_client.table.assert_called_with("pipeline_runs")
    mock_client.table.return_value.select.assert_called_with("status")
    mock_client.table.return_value.select.return_value.eq.assert_called_with(
        "run_id", "run_xyz"
    )


def test_get_run_status_returns_none_when_not_found(repo, mock_client):
    """get_run_status returns None when run does not exist."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    status = repo.get_run_status("run_missing")
    assert status is None


def test_insert_event_inserts_into_pipeline_run_events(repo, mock_client):
    """Insert event adds row with run_id, event_type, optional payload."""
    repo.insert_event(
        run_id="run_1",
        event_type="pipeline_succeeded",
        event_payload_json={"property_count": 12},
    )
    mock_client.table.assert_called_with("pipeline_run_events")
    call_arg = mock_client.table.return_value.insert.call_args[0][0]
    assert call_arg["run_id"] == "run_1"
    assert call_arg["event_type"] == "pipeline_succeeded"
    assert call_arg["event_payload_json"] == {"property_count": 12}
