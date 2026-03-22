"""Unit tests for PostgresRunRepository (mocked Supabase client)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.domain.runs import (
    JobRun,
    PipelineRun,
    StageRun,
    StepRun,
    UsageRecord,
)
from app.repositories.postgres_run_repository import PostgresRunRepository


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def repo(mock_client):
    return PostgresRunRepository(mock_client)


def test_create_run_upserts_job_runs(repo, mock_client):
    """create_run upserts into job_runs with correct row."""
    mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    repo.create_run(
        job_id="loc_abc",
        run_id="run-uuid-123",
        status="pending",
        owner_user_id="871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
        keywords="coffee shop",
        job_definition_id="job_notion_place_inserter",
        trigger_id="trigger_http_locations",
        target_id="target_places_to_visit",
        definition_snapshot_ref="job_snapshot:abc",
    )
    mock_client.table.assert_any_call("job_runs")
    call_arg = mock_client.table.return_value.upsert.call_args[0][0]
    assert call_arg["id"] == "run-uuid-123"
    assert call_arg["platform_job_id"] == "loc_abc"
    assert call_arg["job_id"] == "job_notion_place_inserter"
    assert call_arg["status"] == "pending"
    assert call_arg["trigger_payload"] == {
        "keywords": "coffee shop",
        "raw_input": "coffee shop",
    }


def test_update_job_status_finds_and_saves(repo, mock_client):
    """update_job_status finds run by platform_job_id and saves updated run."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "run-123",
            "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
            "job_id": "job1",
            "trigger_id": "t1",
            "target_id": "t2",
            "status": "running",
            "trigger_payload": {},
            "platform_job_id": "loc_abc",
            "retry_count": 0,
        }]
    )
    mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    now = datetime.now(timezone.utc)
    repo.update_job_status(
        job_id="loc_abc",
        status="succeeded",
        completed_at=now,
    )
    upsert_call = mock_client.table.return_value.upsert.call_args[0][0]
    assert upsert_call["status"] == "succeeded"
    assert upsert_call["completed_at"] == now.isoformat()


def test_get_run_status_returns_status_when_found(repo, mock_client):
    """get_run_status returns status when run exists."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "run-123",
            "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
            "job_id": "job1",
            "trigger_id": "t1",
            "target_id": "t2",
            "status": "succeeded",
            "trigger_payload": {},
            "platform_job_id": "loc_abc",
            "retry_count": 0,
        }]
    )
    status = repo.get_run_status("run-123")
    assert status == "succeeded"


def test_get_run_status_returns_none_when_not_found(repo, mock_client):
    """get_run_status returns None when run does not exist."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    status = repo.get_run_status("run-missing")
    assert status is None


def test_get_job_retry_count_returns_count_when_found(repo, mock_client):
    """get_job_retry_count returns retry_count when run exists."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"retry_count": 2, "id": "r1", "owner_user_id": "u1", "job_id": "j1", "trigger_id": "t1", "target_id": "t2", "status": "failed", "trigger_payload": {}}]
    )
    count = repo.get_job_retry_count("loc_abc")
    assert count == 2


def test_get_job_retry_count_returns_zero_when_not_found(repo, mock_client):
    """get_job_retry_count returns 0 when run does not exist."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    count = repo.get_job_retry_count("loc_missing")
    assert count == 0


def test_save_job_run_upserts(repo, mock_client):
    """save_job_run upserts JobRun into job_runs."""
    mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    run = JobRun(
        id="run-uuid",
        owner_user_id="871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
        job_id="job1",
        trigger_id="t1",
        target_id="t2",
        status="pending",
        trigger_payload={"raw_input": "coffee"},
        platform_job_id="loc_xyz",
        retry_count=0,
    )
    repo.save_job_run(run)
    mock_client.table.assert_any_call("job_runs")
    call_arg = mock_client.table.return_value.upsert.call_args[0][0]
    assert call_arg["id"] == "run-uuid"
    assert call_arg["status"] == "pending"


def test_list_job_runs_by_owner_returns_runs(repo, mock_client):
    """list_job_runs_by_owner returns JobRuns for owner."""
    mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "run-1",
                "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
                "job_id": "job1",
                "trigger_id": "t1",
                "target_id": "t2",
                "status": "succeeded",
                "trigger_payload": {},
                "platform_job_id": "loc_1",
                "retry_count": 0,
            },
        ]
    )
    runs = repo.list_job_runs_by_owner("871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")
    assert len(runs) == 1
    assert runs[0].id == "run-1"
    assert runs[0].status == "succeeded"


def test_list_recent_job_runs_global_order_and_range(repo, mock_client):
    """list_recent_job_runs queries job_runs without owner filter, newest first."""
    mock_client.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "run-2",
                "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
                "job_id": "job1",
                "trigger_id": "t1",
                "target_id": "t2",
                "status": "succeeded",
                "trigger_payload": {},
                "platform_job_id": "loc_2",
                "retry_count": 0,
            },
        ]
    )
    runs = repo.list_recent_job_runs(limit=10, offset=0)
    assert len(runs) == 1
    assert runs[0].id == "run-2"
    mock_client.table.assert_called_with("job_runs")
    chain = mock_client.table.return_value.select.return_value
    chain.order.assert_called_once()
    chain.order.return_value.range.assert_called_once_with(0, 9)


def test_list_recent_job_runs_filters_by_owner_ids(repo, mock_client):
    """list_recent_job_runs uses in_ when owner_user_ids is non-empty."""
    uid = "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde"
    mock_client.table.return_value.select.return_value.in_.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(
        data=[]
    )
    repo.list_recent_job_runs(limit=5, owner_user_ids=[uid])
    mock_client.table.return_value.select.return_value.in_.assert_called_once()
    call_kw = mock_client.table.return_value.select.return_value.in_.call_args
    assert call_kw[0][0] == "owner_user_id"


def test_insert_event_logs_and_does_not_raise(repo):
    """insert_event logs event and does not raise (Phase 4 logs-only observability)."""
    repo.insert_event("run-123", "pipeline_started", {"job_id": "job1"})
    # No exception; implementation logs only


def test_save_job_run_raises_on_invalid_status(repo, mock_client):
    """save_job_run raises ValueError when status is not a valid run_status_enum value."""
    from app.domain.runs import JobRun

    run = JobRun(
        id="run-uuid",
        owner_user_id="871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
        job_id="job1",
        trigger_id="t1",
        target_id="t2",
        status="invalid_status",
        trigger_payload={},
        platform_job_id="loc_xyz",
        retry_count=0,
    )
    with pytest.raises(ValueError, match="invalid run status"):
        repo.save_job_run(run)
    mock_client.table.return_value.upsert.assert_not_called()


def _assert_all_uuid_fields_are_strings(row: dict) -> None:
    """Assert no UUID objects in row (all must be JSON-serializable strings)."""
    for key, val in row.items():
        assert not isinstance(val, uuid.UUID), f"row[{key!r}] must be str, got {type(val).__name__}"


@patch("app.repositories.postgres_run_repository.resolve_or_create_mapping")
def test_save_stage_run_emits_string_uuids(mock_resolve, repo, mock_client):
    """save_stage_run row payload contains string UUIDs, not UUID objects."""
    mock_resolve.return_value = uuid.UUID("a1b2c3d4-e5f6-4789-a012-3456789abcde")
    mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    run = StageRun(
        id="run_07cfee18_stage_stage_research",
        job_run_id="07cfee18-272f-4969-a817-0c37f8e4f0e0",
        stage_id="stage_research",
        status="running",
        owner_user_id="871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
    )
    repo.save_stage_run(run)
    call_arg = mock_client.table.return_value.upsert.call_args[0][0]
    _assert_all_uuid_fields_are_strings(call_arg)
    assert call_arg["id"] == "a1b2c3d4-e5f6-4789-a012-3456789abcde"
    assert call_arg["job_run_id"] == "07cfee18-272f-4969-a817-0c37f8e4f0e0"


@patch("app.repositories.postgres_run_repository.resolve_or_create_mapping")
def test_save_pipeline_run_emits_string_uuids(mock_resolve, repo, mock_client):
    """save_pipeline_run row payload contains string UUIDs, not UUID objects."""
    mock_resolve.side_effect = [
        uuid.UUID("b2c3d4e5-f6a7-4890-b123-456789abcdef"),
        uuid.UUID("c3d4e5f6-a7b8-4901-c234-56789abcdef0"),
    ]
    mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    run = PipelineRun(
        id="run_07cfee18_pipeline_pipeline_research",
        stage_run_id="run_07cfee18_stage_stage_research",
        pipeline_id="pipeline_research",
        status="running",
        owner_user_id="871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
        job_run_id="07cfee18-272f-4969-a817-0c37f8e4f0e0",
    )
    repo.save_pipeline_run(run)
    call_arg = mock_client.table.return_value.upsert.call_args[0][0]
    _assert_all_uuid_fields_are_strings(call_arg)
    assert call_arg["stage_run_id"] == "b2c3d4e5-f6a7-4890-b123-456789abcdef"
    assert call_arg["job_run_id"] == "07cfee18-272f-4969-a817-0c37f8e4f0e0"


@patch("app.repositories.postgres_run_repository.resolve_or_create_mapping")
def test_save_step_run_emits_string_uuids(mock_resolve, repo, mock_client):
    """save_step_run row payload contains string UUIDs, not UUID objects."""
    mock_resolve.side_effect = [
        uuid.UUID("d4e5f6a7-b8c9-4012-d345-6789abcdef01"),
        uuid.UUID("e5f6a7b8-c9d0-4123-e456-789abcdef012"),
        uuid.UUID("f6a7b8c9-d0e1-4234-f567-89abcdef0123"),
    ]
    mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    run = StepRun(
        id="run_07cfee18_step_step_optimize_query",
        pipeline_run_id="run_07cfee18_pipeline_pipeline_research",
        step_id="step_optimize_query",
        step_template_id="step_template_optimize_input_claude",
        status="running",
        owner_user_id="871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
        job_run_id="07cfee18-272f-4969-a817-0c37f8e4f0e0",
        stage_run_id="run_07cfee18_stage_stage_research",
    )
    repo.save_step_run(run)
    call_arg = mock_client.table.return_value.upsert.call_args[0][0]
    _assert_all_uuid_fields_are_strings(call_arg)
    assert call_arg["job_run_id"] == "07cfee18-272f-4969-a817-0c37f8e4f0e0"
    assert call_arg["processing_log"] == []


@patch("app.repositories.postgres_run_repository.resolve_or_create_mapping")
def test_save_step_run_includes_processing_log(mock_resolve, repo, mock_client):
    mock_resolve.side_effect = [
        uuid.UUID("d4e5f6a7-b8c9-4012-d345-6789abcdef01"),
        uuid.UUID("e5f6a7b8-c9d0-4123-e456-789abcdef012"),
        uuid.UUID("f6a7b8c9-d0e1-4234-f567-89abcdef0123"),
    ]
    mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    run = StepRun(
        id="run_07cfee18_step_step_optimize_query",
        pipeline_run_id="run_07cfee18_pipeline_pipeline_research",
        step_id="step_optimize_query",
        step_template_id="step_template_optimize_input_claude",
        status="succeeded",
        owner_user_id="871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
        job_run_id="07cfee18-272f-4969-a817-0c37f8e4f0e0",
        stage_run_id="run_07cfee18_stage_stage_research",
        processing_log=["line1", "line2"],
    )
    repo.save_step_run(run)
    call_arg = mock_client.table.return_value.upsert.call_args[0][0]
    assert call_arg["processing_log"] == ["line1", "line2"]


def test_list_step_runs_for_job_run_orders_and_joins_pipeline(repo, mock_client):
    """list_step_runs_for_job_run queries step_runs and enriches pipeline_id."""
    job_uuid = "07cfee18-272f-4969-a817-0c37f8e4f0e0"
    pr_uuid = "11111111-2222-4333-8444-555555555555"
    step_table = MagicMock()
    pipe_table = MagicMock()
    mock_client.table.side_effect = lambda name: step_table if name == "step_runs" else pipe_table

    step_table.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "aaaa1111-1111-4111-8111-111111111111",
                "pipeline_run_id": pr_uuid,
                "step_id": "s1",
                "step_template_id": "t1",
                "job_run_id": job_uuid,
                "stage_run_id": "bbbb2222-2222-4222-8222-222222222222",
                "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
                "status": "succeeded",
                "input_summary": {"schema_version": 1},
                "output_summary": {"schema_version": 1},
                "processing_log": ["p1"],
                "started_at": None,
                "completed_at": None,
                "error_summary": None,
                "created_at": "2026-01-01T00:00:00Z",
            }
        ]
    )
    pipe_table.select.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[{"id": pr_uuid, "pipeline_id": "pipe_a"}]
    )

    out = repo.list_step_runs_for_job_run(job_uuid, "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")
    assert len(out) == 1
    assert out[0].step_id == "s1"
    assert out[0].pipeline_id == "pipe_a"
    assert out[0].processing_log == ["p1"]


@patch("app.repositories.postgres_run_repository.resolve_or_create_mapping")
def test_save_usage_record_emits_string_uuids(mock_resolve, repo, mock_client):
    """save_usage_record row payload contains string UUIDs, not UUID objects."""
    mock_resolve.side_effect = [
        uuid.UUID("a7b8c9d0-e1f2-4345-a678-9abcdef01234"),
        uuid.UUID("b8c9d0e1-f2a3-4456-b789-abcdef012345"),
    ]
    mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock()
    record = UsageRecord(
        id="usage_7f00afcd6b3d",
        job_run_id="07cfee18-272f-4969-a817-0c37f8e4f0e0",
        usage_type="llm_tokens",
        provider="anthropic",
        metric_name="total_tokens",
        metric_value=100,
        owner_user_id="871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
        step_run_id="run_07cfee18_step_step_optimize_query",
        metadata={"prompt_tokens": 50, "completion_tokens": 50},
    )
    repo.save_usage_record(record)
    call_arg = mock_client.table.return_value.insert.call_args[0][0]
    _assert_all_uuid_fields_are_strings(call_arg)
    assert call_arg["job_run_id"] == "07cfee18-272f-4969-a817-0c37f8e4f0e0"
    assert call_arg["step_run_id"] == "a7b8c9d0-e1f2-4345-a678-9abcdef01234"


@patch("app.repositories.postgres_run_repository.resolve_or_create_mapping")
def test_save_usage_record_without_step_run_id_emits_string_uuids(mock_resolve, repo, mock_client):
    """save_usage_record with step_run_id=None still emits JSON-serializable row."""
    mock_resolve.return_value = uuid.UUID("c9d0e1f2-a3b4-4567-c890-bcdef0123456")
    mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock()
    record = UsageRecord(
        id="usage_abc123",
        job_run_id="07cfee18-272f-4969-a817-0c37f8e4f0e0",
        usage_type="external_api_call",
        provider="google_places",
        metric_name="search_places",
        metric_value=1,
        owner_user_id="871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
        step_run_id=None,
    )
    repo.save_usage_record(record)
    call_arg = mock_client.table.return_value.insert.call_args[0][0]
    _assert_all_uuid_fields_are_strings(call_arg)
    assert call_arg["step_run_id"] is None
