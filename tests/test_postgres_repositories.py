"""Unit tests for Postgres definition repositories (Phase 4 p4_pr03)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.domain import (
    ConnectorTemplate,
    DataTarget,
    JobDefinition,
    TriggerDefinition,
)
from app.domain.jobs import PipelineDefinition, StageDefinition, StepInstance
from app.repositories.postgres_repositories import (
    PostgresConnectorTemplateRepository,
    PostgresJobRepository,
    PostgresTargetRepository,
    PostgresTargetSchemaRepository,
    PostgresTriggerRepository,
)
from app.services.validation_service import JobGraph


@pytest.fixture
def mock_client():
    return MagicMock()


# ---- PostgresConnectorTemplateRepository ----
def test_postgres_connector_template_get_by_id_returns_template(mock_client):
    """PostgresConnectorTemplateRepository get_by_id returns ConnectorTemplate when found."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "conn_notion",
            "slug": "notion_oauth",
            "display_name": "Notion",
            "connector_type": "notion_oauth",
            "provider": "notion",
            "auth_strategy": "oauth2",
            "capabilities": [],
            "config_schema": {},
            "secret_schema": {},
            "status": "active",
            "visibility": "platform",
        }]
    )
    repo = PostgresConnectorTemplateRepository(mock_client)
    t = repo.get_by_id("conn_notion")
    assert t is not None
    assert isinstance(t, ConnectorTemplate)
    assert t.id == "conn_notion"
    assert t.provider == "notion"


def test_postgres_connector_template_get_by_id_returns_none_when_empty(mock_client):
    """PostgresConnectorTemplateRepository get_by_id returns None when not found."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    repo = PostgresConnectorTemplateRepository(mock_client)
    t = repo.get_by_id("conn_missing")
    assert t is None


def test_postgres_connector_template_list_all(mock_client):
    """PostgresConnectorTemplateRepository list_all returns all templates."""
    mock_client.table.return_value.select.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "c1", "slug": "s1", "display_name": "C1", "connector_type": "t1", "provider": "p1", "auth_strategy": "a1", "capabilities": [], "config_schema": {}, "secret_schema": {}, "status": "active", "visibility": "platform"},
            {"id": "c2", "slug": "s2", "display_name": "C2", "connector_type": "t2", "provider": "p2", "auth_strategy": "a2", "capabilities": [], "config_schema": {}, "secret_schema": {}, "status": "active", "visibility": "platform"},
        ]
    )
    repo = PostgresConnectorTemplateRepository(mock_client)
    templates = repo.list_all()
    assert len(templates) == 2
    assert templates[0].id == "c1"
    assert templates[1].id == "c2"


def test_postgres_connector_template_save_upserts(mock_client):
    """PostgresConnectorTemplateRepository save upserts template."""
    mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    repo = PostgresConnectorTemplateRepository(mock_client)
    t = ConnectorTemplate(
        id="conn_test",
        slug="test",
        display_name="Test",
        connector_type="oauth",
        provider="test",
        auth_strategy="oauth2",
        capabilities=[],
        config_schema={},
        secret_schema={},
        status="active",
        visibility="platform",
    )
    repo.save(t)
    mock_client.table.assert_called_with("connector_templates")
    call_arg = mock_client.table.return_value.upsert.call_args[0][0]
    assert call_arg["id"] == "conn_test"
    assert call_arg["provider"] == "test"


# ---- PostgresTriggerRepository ----
def test_postgres_trigger_get_by_id_returns_trigger(mock_client):
    """PostgresTriggerRepository get_by_id returns TriggerDefinition when found."""
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "trigger_http_locations",
            "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
            "trigger_type": "http",
            "display_name": "Locations",
            "path": "locations",
            "method": "POST",
            "request_body_schema": {},
            "status": "active",
            "auth_mode": "bearer",
            "visibility": "owner",
        }]
    )
    repo = PostgresTriggerRepository(mock_client)
    t = repo.get_by_id("trigger_http_locations", "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")
    assert t is not None
    assert isinstance(t, TriggerDefinition)
    assert t.id == "trigger_http_locations"
    assert t.path == "locations"


def test_postgres_trigger_get_by_path_returns_trigger(mock_client):
    """PostgresTriggerRepository get_by_path returns TriggerDefinition when found."""
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "trigger_http_locations",
            "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
            "trigger_type": "http",
            "display_name": "Locations",
            "path": "locations",
            "method": "POST",
            "request_body_schema": {},
            "status": "active",
            "auth_mode": "bearer",
            "visibility": "owner",
        }]
    )
    repo = PostgresTriggerRepository(mock_client)
    t = repo.get_by_path("locations", "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")
    assert t is not None
    assert t.path == "locations"


def test_postgres_trigger_get_by_id_returns_none_when_empty(mock_client):
    """PostgresTriggerRepository get_by_id returns None when not found."""
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    repo = PostgresTriggerRepository(mock_client)
    t = repo.get_by_id("trigger_missing", "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")
    assert t is None


# ---- PostgresJobRepository ----
def test_postgres_job_get_graph_by_id_returns_full_graph(mock_client):
    """PostgresJobRepository get_graph_by_id returns JobGraph with job, stages, pipelines, steps."""
    # Job row
    job_exec = MagicMock()
    job_exec.data = [{
        "id": "job_test",
        "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
        "display_name": "Test Job",
        "target_id": "target_1",
        "status": "active",
        "stage_ids": ["stage_1"],
        "visibility": "owner",
    }]
    # Stages
    stages_exec = MagicMock()
    stages_exec.data = [{
        "id": "stage_1",
        "job_id": "job_test",
        "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
        "display_name": "Stage 1",
        "sequence": 0,
        "pipeline_ids": ["pipe_1"],
        "pipeline_run_mode": "parallel",
    }]
    # Pipelines
    pipes_exec = MagicMock()
    pipes_exec.data = [{
        "id": "pipe_1",
        "stage_id": "stage_1",
        "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
        "display_name": "Pipe 1",
        "sequence": 0,
        "step_ids": ["step_1"],
        "purpose": None,
    }]
    # Steps
    steps_exec = MagicMock()
    steps_exec.data = [{
        "id": "step_1",
        "pipeline_id": "pipe_1",
        "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
        "step_template_id": "step_opt",
        "display_name": "Optimize",
        "sequence": 0,
        "input_bindings": {},
        "config": {},
        "failure_policy": None,
    }]

    def table_side_effect(name):
        t = MagicMock()
        if name == "job_definitions":
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = job_exec
        elif name == "stage_definitions":
            t.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = stages_exec
        elif name == "pipeline_definitions":
            t.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = pipes_exec
        elif name == "step_instances":
            t.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = steps_exec
        return t

    mock_client.table.side_effect = table_side_effect
    repo = PostgresJobRepository(mock_client)
    graph = repo.get_graph_by_id("job_test", "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")
    assert graph is not None
    assert isinstance(graph, JobGraph)
    assert graph.job.id == "job_test"
    assert len(graph.stages) == 1
    assert graph.stages[0].id == "stage_1"
    assert len(graph.pipelines) == 1
    assert graph.pipelines[0].id == "pipe_1"
    assert len(graph.steps) == 1
    assert graph.steps[0].id == "step_1"


def test_postgres_job_get_graph_by_id_returns_none_when_job_missing(mock_client):
    """PostgresJobRepository get_graph_by_id returns None when job not found."""
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    repo = PostgresJobRepository(mock_client)
    graph = repo.get_graph_by_id("job_missing", "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")
    assert graph is None


def test_postgres_job_get_by_id_delegates_to_get_graph(mock_client):
    """PostgresJobRepository get_by_id returns job from get_graph_by_id."""
    job_row = {
        "id": "job_test",
        "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
        "display_name": "Test",
        "target_id": "t2",
        "status": "active",
        "stage_ids": [],
        "visibility": "owner",
    }
    job_exec = MagicMock(data=[job_row])
    stages_exec = MagicMock(data=[])
    pipes_exec = MagicMock(data=[])
    steps_exec = MagicMock(data=[])

    def make_table_mock(table_name):
        t = MagicMock()
        chain = t.select.return_value.eq.return_value
        if table_name == "job_definitions":
            chain.eq.return_value.limit.return_value.execute.return_value = job_exec
        elif table_name == "stage_definitions":
            chain.eq.return_value.order.return_value.execute.return_value = stages_exec
        elif table_name == "pipeline_definitions":
            chain.eq.return_value.order.return_value.execute.return_value = pipes_exec
        elif table_name == "step_instances":
            chain.eq.return_value.order.return_value.execute.return_value = steps_exec
        return t

    mock_client.table.side_effect = make_table_mock
    repo = PostgresJobRepository(mock_client)
    job = repo.get_by_id("job_test", "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")
    assert job is not None
    assert job.id == "job_test"


def test_postgres_job_save_job_graph_upserts_job_stages_pipelines_steps(mock_client):
    """PostgresJobRepository save_job_graph upserts job, stages, pipelines, steps."""
    mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    job = JobDefinition(
        id="job_save",
        owner_user_id="871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
        display_name="Save Test",
        target_id="t2",
        status="active",
        stage_ids=["s1"],
        visibility="owner",
    )
    stage = StageDefinition(
        id="s1",
        job_id="job_save",
        display_name="S1",
        sequence=0,
        pipeline_ids=["p1"],
        pipeline_run_mode="parallel",
    )
    pipeline = PipelineDefinition(
        id="p1",
        stage_id="s1",
        display_name="P1",
        sequence=0,
        step_ids=["st1"],
        purpose=None,
    )
    step = StepInstance(
        id="st1",
        pipeline_id="p1",
        step_template_id="step_opt",
        display_name="Step",
        sequence=0,
        input_bindings={},
        config={},
    )
    graph = JobGraph(job=job, stages=[stage], pipelines=[pipeline], steps=[step])
    repo = PostgresJobRepository(mock_client)
    repo.save_job_graph(graph, skip_reference_checks=True)
    assert mock_client.table.call_count >= 4
    tables_called = [c[0][0] for c in mock_client.table.call_args_list]
    assert "job_definitions" in tables_called
    assert "stage_definitions" in tables_called
    assert "pipeline_definitions" in tables_called
    assert "step_instances" in tables_called


# ---- PostgresTargetRepository ----
def test_postgres_target_get_by_id_returns_target(mock_client):
    """PostgresTargetRepository get_by_id returns DataTarget when found."""
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "target_places",
            "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
            "target_template_id": "notion_database",
            "connector_instance_id": "conn_1",
            "display_name": "Places",
            "external_target_id": "ext_1",
            "status": "active",
            "visibility": "owner",
        }]
    )
    repo = PostgresTargetRepository(mock_client)
    t = repo.get_by_id("target_places", "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")
    assert t is not None
    assert isinstance(t, DataTarget)
    assert t.id == "target_places"
    assert t.external_target_id == "ext_1"


def test_postgres_target_list_by_owner_returns_list(mock_client):
    """PostgresTargetRepository list_by_owner returns targets for owner."""
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "t1", "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde", "target_template_id": "tt1", "connector_instance_id": "c1", "display_name": "T1", "external_target_id": "e1", "status": "active", "visibility": "owner"},
        ]
    )
    repo = PostgresTargetRepository(mock_client)
    targets = repo.list_by_owner("871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")
    assert len(targets) == 1
    assert targets[0].id == "t1"


# ---- PostgresTargetSchemaRepository ----
def test_postgres_target_schema_get_by_id_returns_snapshot(mock_client):
    """PostgresTargetSchemaRepository get_by_id returns TargetSchemaSnapshot when found."""
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "schema_1",
            "owner_user_id": "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde",
            "data_target_id": "target_1",
            "version": "1",
            "fetched_at": "2026-01-01T00:00:00Z",
            "is_active": True,
            "source_connector_instance_id": "conn_1",
            "properties": [],
        }]
    )
    repo = PostgresTargetSchemaRepository(mock_client)
    s = repo.get_by_id("schema_1", "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")
    assert s is not None
    assert s.id == "schema_1"
    assert s.data_target_id == "target_1"
