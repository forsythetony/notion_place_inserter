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
from app.services.validation_service import (
    JobGraph,
    ValidationError,
    ValidationService,
    collect_input_contract_metadata_errors,
    collect_output_contract_metadata_errors,
)


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


def test_parse_step_template_preserves_output_contract_field_metadata():
    """Nested keys under output_contract.fields (title, summary, example, pick_hint) are preserved."""
    data = {
        "id": "step_meta",
        "slug": "meta",
        "display_name": "Meta",
        "step_kind": "lookup",
        "description": "",
        "input_contract": {},
        "output_contract": {
            "fields": {
                "foo": {
                    "type": "object",
                    "title": "Foo title",
                    "summary": "Short",
                    "pick_hint": "Hint",
                    "example": {"a": 1},
                }
            }
        },
        "config_schema": {},
        "runtime_binding": "x",
        "category": "lookup",
        "status": "active",
    }
    t = parse_step_template(data)
    foo = t.output_contract["fields"]["foo"]
    assert foo["title"] == "Foo title"
    assert foo["summary"] == "Short"
    assert foo["pick_hint"] == "Hint"
    assert foo["example"] == {"a": 1}
    assert collect_output_contract_metadata_errors(t.output_contract, template_id=t.id) == []


def test_parse_step_template_preserves_input_contract_field_title():
    """Nested keys under input_contract.fields (title, etc.) are preserved."""
    data = {
        "id": "step_in_meta",
        "slug": "in_meta",
        "display_name": "In Meta",
        "step_kind": "lookup",
        "description": "",
        "input_contract": {
            "fields": {
                "value": {
                    "type": "string",
                    "title": "Image URL",
                }
            }
        },
        "output_contract": {},
        "config_schema": {},
        "runtime_binding": "x",
        "category": "lookup",
        "status": "active",
    }
    t = parse_step_template(data)
    assert t.input_contract["fields"]["value"]["title"] == "Image URL"
    assert collect_input_contract_metadata_errors(t.input_contract, template_id=t.id) == []


async def test_yaml_connector_template_repository_list_all():
    """YamlConnectorTemplateRepository lists catalog connector templates."""
    repo = YamlConnectorTemplateRepository()
    templates = await repo.list_all()
    assert len(templates) >= 3
    ids = {t.id for t in templates}
    assert "notion_oauth_workspace" in ids
    assert "google_places_api" in ids
    assert "claude_api" in ids


async def test_yaml_connector_template_repository_get_by_id():
    """YamlConnectorTemplateRepository get_by_id returns template."""
    repo = YamlConnectorTemplateRepository()
    t = await repo.get_by_id("notion_oauth_workspace")
    assert t is not None
    assert t.id == "notion_oauth_workspace"
    assert t.provider == "notion"


async def test_yaml_target_template_repository_list_all():
    """YamlTargetTemplateRepository lists catalog target templates."""
    repo = YamlTargetTemplateRepository()
    templates = await repo.list_all()
    assert len(templates) >= 1
    assert any(t.id == "notion_database" for t in templates)


async def test_yaml_target_template_repository_get_by_id():
    """YamlTargetTemplateRepository get_by_id returns template."""
    repo = YamlTargetTemplateRepository()
    t = await repo.get_by_id("notion_database")
    assert t is not None
    assert t.target_kind == "notion_database"


async def test_yaml_step_template_repository_list_all():
    """YamlStepTemplateRepository lists catalog step templates."""
    repo = YamlStepTemplateRepository()
    templates = await repo.list_all()
    assert len(templates) >= 7


async def test_yaml_step_template_repository_get_by_id():
    """YamlStepTemplateRepository get_by_id returns template."""
    repo = YamlStepTemplateRepository()
    t = await repo.get_by_id("step_template_optimize_input_claude")
    assert t is not None
    assert t.step_kind == "optimize_input"


async def test_yaml_job_repository_get_bootstrap_job():
    """YamlJobRepository get_bootstrap_job returns Notion Place Inserter."""
    repo = YamlJobRepository()
    job = await repo.get_bootstrap_job("notion_place_inserter")
    assert job is not None
    assert job.id == "job_notion_place_inserter"
    assert job.display_name == "Notion Place Inserter"
    assert len(job.stage_ids) >= 2


async def test_yaml_job_repository_get_bootstrap_job_missing_returns_none():
    """YamlJobRepository get_bootstrap_job returns None for missing slug."""
    repo = YamlJobRepository()
    job = await repo.get_bootstrap_job("nonexistent")
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
    for stage in graph.stages:
        assert stage.pipeline_run_mode == "parallel", (
            f"Bootstrap stage {stage.id} expected parallel (default), got {stage.pipeline_run_mode}"
        )


async def test_yaml_job_repository_get_graph_by_id():
    """YamlJobRepository get_graph_by_id returns full JobGraph for bootstrap job."""
    repo = YamlJobRepository()
    graph = await repo.get_graph_by_id("job_notion_place_inserter", "user_1")
    assert graph is not None
    assert graph.job.id == "job_notion_place_inserter"
    assert len(graph.stages) >= 2
    assert len(graph.pipelines) >= 2
    assert len(graph.steps) >= 6


async def test_yaml_job_repository_get_graph_by_id_missing_returns_none():
    """YamlJobRepository get_graph_by_id returns None for unknown job."""
    repo = YamlJobRepository()
    graph = await repo.get_graph_by_id("job_nonexistent", "user_1")
    assert graph is None


async def test_yaml_job_repository_save_job_graph_rejects_invalid_job():
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
            target_id="d1",
            status="active",
            stage_ids=[],
        )
        graph = JobGraph(job=job, stages=[], pipelines=[], steps=[])
        with pytest.raises(ValidationError) as exc_info:
            await job_repo.save_job_graph(graph)
        assert "at least one stage" in str(exc_info.value).lower()
        # File should not be created
        job_path = Path(base) / "tenants" / "u1" / "jobs" / "j_invalid.yaml"
        assert not job_path.exists()


async def test_yaml_job_repository_save_job_graph_accepts_valid_job():
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
        await job_repo.save_job_graph(graph, skip_reference_checks=True)
        job_path = Path(base) / "tenants" / "u1" / "jobs" / "job_notion_place_inserter.yaml"
        assert job_path.exists()


async def test_yaml_trigger_repository_save_rejects_invalid_trigger():
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
            auth_mode="bearer",
            secret_value="placeholder",
        )
        with pytest.raises(ValidationError) as exc_info:
            await trigger_repo.save(trigger)
        assert "path" in str(exc_info.value).lower()
        trigger_path = Path(base) / "tenants" / "u1" / "triggers" / "t1.yaml"
        assert not trigger_path.exists()


async def test_yaml_trigger_repository_save_accepts_valid_trigger():
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
            auth_mode="bearer",
            secret_value="yaml_test_secret",
        )
        await trigger_repo.save(trigger)
        loaded = await trigger_repo.get_by_id("t1", "u1")
        assert loaded is not None
        assert loaded.path == "/test"
        await trigger_repo.delete("t1", "u1")
