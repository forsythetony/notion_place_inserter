"""Tests for JobDefinitionService with Postgres-backed repositories (Phase 4 p4_pr03)."""

from unittest.mock import AsyncMock, MagicMock

from app.repositories.postgres_repositories import (
    PostgresJobRepository,
    PostgresTargetRepository,
    PostgresTargetSchemaRepository,
    PostgresTriggerRepository,
)
from app.services.job_definition_service import JobDefinitionService, ResolvedJobSnapshot
from app.services.target_service import TargetService
from app.services.trigger_service import TriggerService


def _trigger_row(owner: str) -> dict:
    return {
        "id": "trigger_http_locations",
        "owner_user_id": owner,
        "trigger_type": "http",
        "display_name": "Locations",
        "path": "locations",
        "method": "POST",
        "request_body_schema": {},
        "status": "active",
        "job_id": "job_test",
        "auth_mode": "bearer",
        "secret_value": "trigger_secret_abc",
        "visibility": "owner",
    }


async def test_job_definition_service_postgres_resolves_snapshot_when_all_present():
    """JobDefinitionService with Postgres repos resolves snapshot when job, trigger, target exist."""
    owner = "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde"
    mock_client = MagicMock()

    job_repo = PostgresJobRepository(mock_client)
    job_exec = MagicMock(
        data=[{
            "id": "job_test",
            "owner_user_id": owner,
            "display_name": "Test",
            "target_id": "target_places_to_visit",
            "status": "active",
            "stage_ids": ["stage_1"],
            "visibility": "owner",
        }]
    )
    stages_exec = MagicMock(
        data=[{
            "id": "stage_1",
            "job_id": "job_test",
            "owner_user_id": owner,
            "display_name": "S1",
            "sequence": 0,
            "pipeline_ids": ["pipe_1"],
            "pipeline_run_mode": "parallel",
        }]
    )
    pipes_exec = MagicMock(
        data=[{
            "id": "pipe_1",
            "stage_id": "stage_1",
            "owner_user_id": owner,
            "display_name": "P1",
            "sequence": 0,
            "step_ids": ["step_1"],
            "purpose": None,
        }]
    )
    steps_exec = MagicMock(
        data=[{
            "id": "step_1",
            "pipeline_id": "pipe_1",
            "owner_user_id": owner,
            "step_template_id": "step_opt",
            "display_name": "Step",
            "sequence": 0,
            "input_bindings": {},
            "config": {},
            "failure_policy": None,
        }]
    )

    def make_table(name):
        t = MagicMock()
        c = t.select.return_value.eq.return_value
        if name == "job_definitions":
            c.eq.return_value.limit.return_value.execute = AsyncMock(return_value=job_exec)
        elif name == "stage_definitions":
            c.eq.return_value.order.return_value.execute = AsyncMock(return_value=stages_exec)
        elif name == "pipeline_definitions":
            c.eq.return_value.order.return_value.execute = AsyncMock(return_value=pipes_exec)
        elif name == "step_instances":
            c.eq.return_value.order.return_value.execute = AsyncMock(return_value=steps_exec)
        return t

    def table_all(name):
        if name == "trigger_definitions":
            t = MagicMock()
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute = AsyncMock(
                return_value=MagicMock(data=[_trigger_row(owner)])
            )
            return t
        if name == "data_targets":
            t = MagicMock()
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute = AsyncMock(
                return_value=MagicMock(
                    data=[{
                        "id": "target_places_to_visit",
                        "owner_user_id": owner,
                        "target_template_id": "notion_database",
                        "connector_instance_id": "conn_1",
                        "display_name": "Places",
                        "external_target_id": "ext_1",
                        "status": "active",
                        "active_schema_snapshot_id": None,
                        "visibility": "owner",
                    }]
                )
            )
            return t
        if name == "target_schema_snapshots":
            t = MagicMock()
            t.select.return_value.eq.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))
            return t
        return make_table(name)

    mock_client.table.side_effect = table_all

    trigger_repo = PostgresTriggerRepository(mock_client)
    target_repo = PostgresTargetRepository(mock_client)
    schema_repo = PostgresTargetSchemaRepository(mock_client)

    trigger_service = TriggerService(trigger_repository=trigger_repo)
    target_service = TargetService(
        target_repository=target_repo,
        target_schema_repository=schema_repo,
    )
    service = JobDefinitionService(
        job_repository=job_repo,
        trigger_service=trigger_service,
        target_service=target_service,
    )

    snapshot = await service.resolve_for_run("job_test", owner, "trigger_http_locations")
    assert snapshot is not None
    assert isinstance(snapshot, ResolvedJobSnapshot)
    assert snapshot.snapshot_ref.startswith("job_snapshot:871ba2fa-fd5d-4a81-9f0d-0d98b348ccde:job_test:")
    assert "job" in snapshot.snapshot
    assert "trigger" in snapshot.snapshot
    assert "target" in snapshot.snapshot
    assert snapshot.snapshot["job"]["id"] == "job_test"
    assert snapshot.snapshot["trigger"]["id"] == "trigger_http_locations"
    assert snapshot.snapshot["target"]["id"] == "target_places_to_visit"


async def test_job_definition_service_postgres_returns_none_when_job_missing():
    """JobDefinitionService with Postgres repos returns None when job not found."""
    owner = "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde"
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[])
    )
    job_repo = PostgresJobRepository(mock_client)
    trigger_repo = PostgresTriggerRepository(mock_client)
    target_repo = PostgresTargetRepository(mock_client)
    schema_repo = PostgresTargetSchemaRepository(mock_client)
    trigger_service = TriggerService(trigger_repository=trigger_repo)
    target_service = TargetService(
        target_repository=target_repo,
        target_schema_repository=schema_repo,
    )
    service = JobDefinitionService(
        job_repository=job_repo,
        trigger_service=trigger_service,
        target_service=target_service,
    )
    snapshot = await service.resolve_for_run("job_missing", owner, "trigger_http_locations")
    assert snapshot is None
