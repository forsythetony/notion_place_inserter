"""Tests for Phase 3 YAML repositories and parsing (p3_pr03, p3_pr04)."""

import tempfile
from pathlib import Path

import pytest

from app.domain import (
    ConnectorTemplate,
    JobDefinition,
    StepTemplate,
    TargetTemplate,
    TriggerDefinition,
)
from app.repositories import (
    YamlConnectorTemplateRepository,
    YamlJobRepository,
    YamlStepTemplateRepository,
    YamlTargetTemplateRepository,
    YamlTriggerRepository,
)
from app.repositories.yaml_loader import (
    load_yaml_file,
    parse_connector_template,
    parse_job_definition,
    parse_job_graph,
    parse_step_template,
    parse_target_template,
)
from app.services.validation_service import JobGraph, ValidationError, ValidationService


def test_load_yaml_file_bootstrap_job():
    """Bootstrap job YAML loads and parses."""
    data = load_yaml_file("product_model/bootstrap/jobs/notion_place_inserter.yaml")
    assert data is not None
    assert data.get("kind") == "job_definition"
    assert data.get("id") == "job_notion_place_inserter"
    assert "stages" in data


def test_parse_job_definition():
    """parse_job_definition produces JobDefinition with stage_ids."""
    data = {
        "id": "job_test",
        "owner_user_id": "user_1",
        "display_name": "Test Job",
        "trigger_id": "trigger_1",
        "target_id": "target_1",
        "status": "active",
        "stage_ids": ["s1", "s2"],
        "stages": [{"id": "s1"}, {"id": "s2"}],
    }
    job = parse_job_definition(data)
    assert isinstance(job, JobDefinition)
    assert job.id == "job_test"
    assert job.owner_user_id == "user_1"
    assert job.stage_ids == ["s1", "s2"]


def test_parse_job_definition_owner_override():
    """parse_job_definition uses owner_user_id_override for bootstrap."""
    data = {
        "id": "job_bootstrap",
        "owner_user_id": "bootstrap",
        "display_name": "Bootstrap",
        "trigger_id": "t1",
        "target_id": "t2",
        "status": "active",
        "stage_ids": [],
        "stages": [],
    }
    job = parse_job_definition(data, owner_user_id_override="user_abc")
    assert job.owner_user_id == "user_abc"


def test_parse_connector_template():
    """parse_connector_template produces ConnectorTemplate."""
    data = {
        "id": "conn_notion",
        "slug": "notion_oauth",
        "display_name": "Notion",
        "connector_type": "notion_oauth",
        "provider": "notion",
        "auth_strategy": "oauth2",
        "capabilities": ["fetch"],
        "config_schema": {},
        "secret_schema": {},
        "status": "active",
    }
    t = parse_connector_template(data)
    assert isinstance(t, ConnectorTemplate)
    assert t.id == "conn_notion"
    assert t.provider == "notion"


def test_parse_target_template():
    """parse_target_template produces TargetTemplate."""
    data = {
        "id": "target_notion",
        "slug": "notion_database",
        "display_name": "Notion Database",
        "target_kind": "notion_database",
        "required_connector_template_id": "conn_notion",
        "supports_schema_snapshots": True,
        "property_types_supported": ["title"],
    }
    t = parse_target_template(data)
    assert isinstance(t, TargetTemplate)
    assert t.id == "target_notion"
    assert t.target_kind == "notion_database"


def test_parse_step_template():
    """parse_step_template produces StepTemplate."""
    data = {
        "id": "step_opt",
        "slug": "optimize_input",
        "display_name": "Optimize",
        "step_kind": "optimize",
        "description": "Optimize input",
        "input_contract": {},
        "output_contract": {},
        "config_schema": {},
        "runtime_binding": "claude",
        "category": "transform",
        "status": "active",
    }
    t = parse_step_template(data)
    assert isinstance(t, StepTemplate)
    assert t.id == "step_opt"
    assert t.step_kind == "optimize"


def test_yaml_connector_template_repository_list_all():
    """YamlConnectorTemplateRepository lists catalog connector templates."""
    repo = YamlConnectorTemplateRepository()
    templates = repo.list_all()
    assert len(templates) >= 3
    ids = {t.id for t in templates}
    assert "notion_oauth_workspace" in ids
    assert "google_places_api" in ids
    assert "claude_api" in ids


def test_yaml_connector_template_repository_get_by_id():
    """YamlConnectorTemplateRepository get_by_id returns template."""
    repo = YamlConnectorTemplateRepository()
    t = repo.get_by_id("notion_oauth_workspace")
    assert t is not None
    assert t.id == "notion_oauth_workspace"
    assert t.provider == "notion"


def test_yaml_target_template_repository_list_all():
    """YamlTargetTemplateRepository lists catalog target templates."""
    repo = YamlTargetTemplateRepository()
    templates = repo.list_all()
    assert len(templates) >= 1
    assert any(t.id == "notion_database" for t in templates)


def test_yaml_target_template_repository_get_by_id():
    """YamlTargetTemplateRepository get_by_id returns template."""
    repo = YamlTargetTemplateRepository()
    t = repo.get_by_id("notion_database")
    assert t is not None
    assert t.target_kind == "notion_database"


def test_yaml_step_template_repository_list_all():
    """YamlStepTemplateRepository lists catalog step templates."""
    repo = YamlStepTemplateRepository()
    templates = repo.list_all()
    assert len(templates) >= 7


def test_yaml_step_template_repository_get_by_id():
    """YamlStepTemplateRepository get_by_id returns template."""
    repo = YamlStepTemplateRepository()
    t = repo.get_by_id("step_template_optimize_input_claude")
    assert t is not None
    assert t.step_kind == "optimize_input"


def test_yaml_job_repository_get_bootstrap_job():
    """YamlJobRepository get_bootstrap_job returns Notion Place Inserter."""
    repo = YamlJobRepository()
    job = repo.get_bootstrap_job("notion_place_inserter")
    assert job is not None
    assert job.id == "job_notion_place_inserter"
    assert job.display_name == "Notion Place Inserter"
    assert len(job.stage_ids) >= 2


def test_yaml_job_repository_get_bootstrap_job_missing_returns_none():
    """YamlJobRepository get_bootstrap_job returns None for missing slug."""
    repo = YamlJobRepository()
    job = repo.get_bootstrap_job("nonexistent")
    assert job is None


def test_load_yaml_file_missing_returns_none():
    """load_yaml_file returns None for missing file."""
    data = load_yaml_file("product_model/nonexistent/file.yaml")
    assert data is None


def test_parse_job_graph_produces_full_graph():
    """parse_job_graph produces JobGraph with stages, pipelines, steps."""
    data = load_yaml_file("product_model/bootstrap/jobs/notion_place_inserter.yaml")
    assert data is not None
    graph = parse_job_graph(data, owner_user_id_override="user_1")
    assert isinstance(graph, JobGraph)
    assert graph.job.id == "job_notion_place_inserter"
    assert len(graph.stages) >= 2
    assert len(graph.pipelines) >= 2
    assert len(graph.steps) >= 6
    # Bootstrap job uses sequential mode (temporary mitigation for Errno 11)
    for stage in graph.stages:
        assert stage.pipeline_run_mode == "sequential", (
            f"Bootstrap stage {stage.id} expected sequential, got {stage.pipeline_run_mode}"
        )


def test_yaml_job_repository_get_graph_by_id():
    """YamlJobRepository get_graph_by_id returns full JobGraph for bootstrap job."""
    repo = YamlJobRepository()
    graph = repo.get_graph_by_id("job_notion_place_inserter", "user_1")
    assert graph is not None
    assert graph.job.id == "job_notion_place_inserter"
    assert len(graph.stages) >= 2
    assert len(graph.pipelines) >= 2
    assert len(graph.steps) >= 6


def test_yaml_job_repository_get_graph_by_id_missing_returns_none():
    """YamlJobRepository get_graph_by_id returns None for unknown job."""
    repo = YamlJobRepository()
    graph = repo.get_graph_by_id("job_nonexistent", "user_1")
    assert graph is None


def test_yaml_job_repository_save_job_graph_rejects_invalid_job():
    """save_job_graph with validation rejects invalid job before persisting."""
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        Path(base).mkdir(parents=True)
        step_repo = YamlStepTemplateRepository(base="product_model")
        validation = ValidationService(step_template_repo=step_repo)
        job_repo = YamlJobRepository(base=base, validation_service=validation)

        job = JobDefinition(
            id="j_invalid",
            owner_user_id="u1",
            display_name="Invalid",
            trigger_id="t1",
            target_id="d1",
            status="active",
            stage_ids=[],
        )
        graph = JobGraph(job=job, stages=[], pipelines=[], steps=[])
        with pytest.raises(ValidationError) as exc_info:
            job_repo.save_job_graph(graph)
        assert "at least one stage" in str(exc_info.value).lower()
        # File should not be created
        job_path = Path(base) / "tenants" / "u1" / "jobs" / "j_invalid.yaml"
        assert not job_path.exists()


def test_yaml_job_repository_save_job_graph_accepts_valid_job():
    """save_job_graph with validation accepts valid job and persists."""
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        Path(base).mkdir(parents=True)
        step_repo = YamlStepTemplateRepository(base="product_model")
        validation = ValidationService(step_template_repo=step_repo)
        job_repo = YamlJobRepository(base=base, validation_service=validation)

        data = load_yaml_file("product_model/bootstrap/jobs/notion_place_inserter.yaml")
        assert data is not None
        graph = parse_job_graph(data, owner_user_id_override="u1")
        job_repo.save_job_graph(graph, skip_reference_checks=True)
        job_path = Path(base) / "tenants" / "u1" / "jobs" / "job_notion_place_inserter.yaml"
        assert job_path.exists()


def test_yaml_trigger_repository_save_rejects_invalid_trigger():
    """YamlTriggerRepository.save with validation rejects invalid trigger."""
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        Path(base).mkdir(parents=True)
        validation = ValidationService()
        trigger_repo = YamlTriggerRepository(base=base, validation_service=validation)
        trigger = TriggerDefinition(
            id="t1",
            owner_user_id="u1",
            trigger_type="http",
            display_name="T",
            path="",
            method="POST",
            request_body_schema={},
            status="active",
            job_id="j1",
            auth_mode="bearer",
        )
        with pytest.raises(ValidationError) as exc_info:
            trigger_repo.save(trigger)
        assert "path" in str(exc_info.value).lower()
        trigger_path = Path(base) / "tenants" / "u1" / "triggers" / "t1.yaml"
        assert not trigger_path.exists()


def test_yaml_trigger_repository_save_accepts_valid_trigger():
    """YamlTriggerRepository.save persists valid trigger."""
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        Path(base).mkdir(parents=True)
        trigger_repo = YamlTriggerRepository(base=base)
        trigger = TriggerDefinition(
            id="t1",
            owner_user_id="u1",
            trigger_type="http",
            display_name="Test",
            path="/test",
            method="POST",
            request_body_schema={},
            status="active",
            job_id="j1",
            auth_mode="bearer",
        )
        trigger_repo.save(trigger)
        loaded = trigger_repo.get_by_id("t1", "u1")
        assert loaded is not None
        assert loaded.path == "/test"
        trigger_repo.delete("t1", "u1")
