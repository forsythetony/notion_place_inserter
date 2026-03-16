"""Tests for Phase 3 ValidationService (p3_pr04)."""

import tempfile
from pathlib import Path

import pytest

from app.domain import (
    AppLimits,
    DataTarget,
    JobDefinition,
    PipelineDefinition,
    StageDefinition,
    StepInstance,
    StepTemplate,
    TriggerDefinition,
)
from app.repositories import (
    YamlAppConfigRepository,
    YamlConnectorInstanceRepository,
    YamlJobRepository,
    YamlStepTemplateRepository,
    YamlTargetRepository,
    YamlTargetSchemaRepository,
    YamlTargetTemplateRepository,
    YamlTriggerRepository,
)
from app.repositories.yaml_loader import load_yaml_file, parse_job_graph
from app.services.validation_service import JobGraph, ValidationError, ValidationService


def _step_template_repo(base: str | None = None) -> YamlStepTemplateRepository:
    """Step template repo for validation (catalog)."""
    return YamlStepTemplateRepository(base=base or "product_model")


def _validation_service(
    base: str | None = None,
    step_template_repo: YamlStepTemplateRepository | None = None,
    app_config_repo: YamlAppConfigRepository | None = None,
) -> ValidationService:
    """ValidationService with step template repo (minimal for structural checks)."""
    step_repo = step_template_repo or _step_template_repo(base)
    return ValidationService(
        step_template_repo=step_repo,
        app_config_repo=app_config_repo,
    )


def test_validation_service_rejects_job_with_no_stages():
    """Job must have at least one stage."""
    job = JobDefinition(
        id="j1",
        owner_user_id="u1",
        display_name="Empty",
        target_id="d1",
        status="active",
        stage_ids=[],
    )
    graph = JobGraph(job=job, stages=[], pipelines=[], steps=[])
    svc = _validation_service()
    with pytest.raises(ValidationError) as exc_info:
        svc.validate_job_graph(graph)
    assert "at least one stage" in str(exc_info.value).lower()


def test_validation_service_rejects_stage_with_no_pipelines():
    """Stage must have at least one pipeline."""
    job = JobDefinition(
        id="j1",
        owner_user_id="u1",
        display_name="Test",
        target_id="d1",
        status="active",
        stage_ids=["s1"],
    )
    stage = StageDefinition(
        id="s1",
        job_id="j1",
        display_name="S1",
        sequence=1,
        pipeline_ids=[],
    )
    graph = JobGraph(job=job, stages=[stage], pipelines=[], steps=[])
    svc = _validation_service()
    with pytest.raises(ValidationError) as exc_info:
        svc.validate_job_graph(graph)
    assert "at least one pipeline" in str(exc_info.value).lower()


def test_validation_service_rejects_duplicate_stage_sequences():
    """Stage sequences must be unique within job."""
    job = JobDefinition(
        id="j1",
        owner_user_id="u1",
        display_name="Test",
        target_id="d1",
        status="active",
        stage_ids=["s1", "s2"],
    )
    s1 = StageDefinition(id="s1", job_id="j1", display_name="S1", sequence=1, pipeline_ids=["p1"])
    s2 = StageDefinition(id="s2", job_id="j1", display_name="S2", sequence=1, pipeline_ids=["p2"])
    p1 = PipelineDefinition(id="p1", stage_id="s1", display_name="P1", sequence=1, step_ids=["st1"])
    p2 = PipelineDefinition(id="p2", stage_id="s2", display_name="P2", sequence=1, step_ids=["st2"])
    st1 = StepInstance(
        id="st1",
        pipeline_id="p1",
        step_template_id="step_template_cache_set",
        display_name="ST1",
        sequence=1,
        input_bindings={},
        config={"cache_key": "k1"},
    )
    st2 = StepInstance(
        id="st2",
        pipeline_id="p2",
        step_template_id="step_template_cache_set",
        display_name="ST2",
        sequence=1,
        input_bindings={},
        config={"cache_key": "k2"},
    )
    graph = JobGraph(job=job, stages=[s1, s2], pipelines=[p1, p2], steps=[st1, st2])
    svc = _validation_service()
    with pytest.raises(ValidationError) as exc_info:
        svc.validate_job_graph(graph)
    assert "unique" in str(exc_info.value).lower()


def test_validation_service_rejects_property_set_not_final_step():
    """Pipeline must terminate with Cache Set or Property Set."""
    job = JobDefinition(
        id="j1",
        owner_user_id="u1",
        display_name="Test",
        target_id="d1",
        status="active",
        stage_ids=["s1"],
    )
    stage = StageDefinition(
        id="s1",
        job_id="j1",
        display_name="S1",
        sequence=1,
        pipeline_ids=["p1"],
    )
    pipeline = PipelineDefinition(
        id="p1",
        stage_id="s1",
        display_name="P1",
        sequence=1,
        step_ids=["st1", "st2"],
    )
    # st1 is optimize (not terminal), st2 is cache_set (terminal) - but st1 is first, st2 last
    # So the LAST step is cache_set - that's valid. We need the opposite: last step is NOT terminal.
    st1 = StepInstance(
        id="st1",
        pipeline_id="p1",
        step_template_id="step_template_optimize_input_claude",
        display_name="ST1",
        sequence=1,
        input_bindings={},
        config={},
    )
    st2 = StepInstance(
        id="st2",
        pipeline_id="p1",
        step_template_id="step_template_optimize_input_claude",
        display_name="ST2",
        sequence=2,
        input_bindings={},
        config={},
    )
    graph = JobGraph(job=job, stages=[stage], pipelines=[pipeline], steps=[st1, st2])
    svc = _validation_service()
    with pytest.raises(ValidationError) as exc_info:
        svc.validate_job_graph(graph)
    assert "terminate" in str(exc_info.value).lower() or "cache set" in str(exc_info.value).lower()


def test_validation_service_rejects_job_exceeding_stage_limit():
    """Job must not exceed max_stages_per_job."""
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        Path(base).mkdir(parents=True)
        config_path = Path(base) / "tenants" / "u1" / "app_config.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(
            "max_stages_per_job: 1\nmax_pipelines_per_stage: 10\nmax_steps_per_pipeline: 50\n"
        )
        app_repo = YamlAppConfigRepository(base=base)
        limits = app_repo.get_by_owner("u1")
        assert limits is not None
        assert limits.max_stages_per_job == 1

        job = JobDefinition(
            id="j1",
            owner_user_id="u1",
            display_name="Test",
            target_id="d1",
            status="active",
            stage_ids=["s1", "s2"],
        )
        s1 = StageDefinition(id="s1", job_id="j1", display_name="S1", sequence=1, pipeline_ids=["p1"])
        s2 = StageDefinition(id="s2", job_id="j1", display_name="S2", sequence=2, pipeline_ids=["p2"])
        p1 = PipelineDefinition(id="p1", stage_id="s1", display_name="P1", sequence=1, step_ids=["st1"])
        p2 = PipelineDefinition(id="p2", stage_id="s2", display_name="P2", sequence=1, step_ids=["st2"])
        st1 = StepInstance(
            id="st1",
            pipeline_id="p1",
            step_template_id="step_template_cache_set",
            display_name="ST1",
            sequence=1,
            input_bindings={},
            config={"cache_key": "k1"},
        )
        st2 = StepInstance(
            id="st2",
            pipeline_id="p2",
            step_template_id="step_template_cache_set",
            display_name="ST2",
            sequence=1,
            input_bindings={},
            config={"cache_key": "k2"},
        )
        graph = JobGraph(job=job, stages=[s1, s2], pipelines=[p1, p2], steps=[st1, st2])
        svc = _validation_service(base=base, app_config_repo=app_repo)
        with pytest.raises(ValidationError) as exc_info:
            svc.validate_job_graph(graph)
        assert "max_stages" in str(exc_info.value).lower() or "exceeds" in str(exc_info.value).lower()


def test_validation_service_accepts_valid_bootstrap_job():
    """Valid Notion Place Inserter-like job passes validation (skip reference checks)."""
    data = load_yaml_file("product_model/bootstrap/jobs/notion_place_inserter.yaml")
    assert data is not None
    graph = parse_job_graph(data, owner_user_id_override="user_test")
    svc = _validation_service()
    svc.validate_job_graph(graph, skip_reference_checks=True)


def test_validation_service_validate_stage_definition():
    """validate_stage_definition rejects empty pipeline_ids."""
    svc = ValidationService()
    stage = StageDefinition(
        id="s1",
        job_id="j1",
        display_name="S1",
        sequence=1,
        pipeline_ids=[],
    )
    with pytest.raises(ValidationError) as exc_info:
        svc.validate_stage_definition(stage)
    assert "at least one pipeline" in str(exc_info.value).lower()


def test_validation_service_validate_pipeline_definition():
    """validate_pipeline_definition rejects empty step_ids."""
    svc = ValidationService()
    pipeline = PipelineDefinition(
        id="p1",
        stage_id="s1",
        display_name="P1",
        sequence=1,
        step_ids=[],
    )
    with pytest.raises(ValidationError) as exc_info:
        svc.validate_pipeline_definition(pipeline)
    assert "at least one step" in str(exc_info.value).lower()


def test_validation_service_validate_trigger_rejects_empty_path():
    """validate_trigger rejects empty path."""
    svc = ValidationService()
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
        svc.validate_trigger(trigger)
    assert "path" in str(exc_info.value).lower()


def test_validation_error_aggregates_messages():
    """ValidationError can hold multiple error messages."""
    err = ValidationError("validation failed", ["error one", "error two"])
    assert len(err.errors) == 2
    assert "error one" in str(err)
    assert "error two" in str(err)


def test_validation_service_accepts_property_set_page_metadata_cover_image():
    """Property Set with target_kind=page_metadata and target_field=cover_image is valid."""
    job = JobDefinition(
        id="j1",
        owner_user_id="u1",
        display_name="Test",
        target_id="d1",
        status="active",
        stage_ids=["s1"],
    )
    stage = StageDefinition(
        id="s1",
        job_id="j1",
        display_name="S1",
        sequence=1,
        pipeline_ids=["p1"],
    )
    pipeline = PipelineDefinition(
        id="p1",
        stage_id="s1",
        display_name="P1",
        sequence=1,
        step_ids=["st1"],
    )
    st1 = StepInstance(
        id="st1",
        pipeline_id="p1",
        step_template_id="step_template_property_set",
        display_name="ST1",
        sequence=1,
        input_bindings={},
        config={
            "data_target_id": "d1",
            "target_kind": "page_metadata",
            "target_field": "cover_image",
        },
    )
    graph = JobGraph(job=job, stages=[stage], pipelines=[pipeline], steps=[st1])
    svc = _validation_service()
    svc.validate_job_graph(graph, skip_reference_checks=True)


def test_validation_service_accepts_property_set_page_metadata_icon_image():
    """Property Set with target_kind=page_metadata and target_field=icon_image is valid."""
    job = JobDefinition(
        id="j1",
        owner_user_id="u1",
        display_name="Test",
        target_id="d1",
        status="active",
        stage_ids=["s1"],
    )
    stage = StageDefinition(
        id="s1",
        job_id="j1",
        display_name="S1",
        sequence=1,
        pipeline_ids=["p1"],
    )
    pipeline = PipelineDefinition(
        id="p1",
        stage_id="s1",
        display_name="P1",
        sequence=1,
        step_ids=["st1"],
    )
    st1 = StepInstance(
        id="st1",
        pipeline_id="p1",
        step_template_id="step_template_property_set",
        display_name="ST1",
        sequence=1,
        input_bindings={},
        config={
            "data_target_id": "d1",
            "target_kind": "page_metadata",
            "target_field": "icon_image",
        },
    )
    graph = JobGraph(job=job, stages=[stage], pipelines=[pipeline], steps=[st1])
    svc = _validation_service()
    svc.validate_job_graph(graph, skip_reference_checks=True)


def test_validation_service_rejects_property_set_page_metadata_invalid_target_field():
    """Property Set with target_kind=page_metadata and invalid target_field fails."""
    job = JobDefinition(
        id="j1",
        owner_user_id="u1",
        display_name="Test",
        target_id="d1",
        status="active",
        stage_ids=["s1"],
    )
    stage = StageDefinition(
        id="s1",
        job_id="j1",
        display_name="S1",
        sequence=1,
        pipeline_ids=["p1"],
    )
    pipeline = PipelineDefinition(
        id="p1",
        stage_id="s1",
        display_name="P1",
        sequence=1,
        step_ids=["st1"],
    )
    st1 = StepInstance(
        id="st1",
        pipeline_id="p1",
        step_template_id="step_template_property_set",
        display_name="ST1",
        sequence=1,
        input_bindings={},
        config={
            "data_target_id": "d1",
            "target_kind": "page_metadata",
            "target_field": "invalid_field",
        },
    )
    graph = JobGraph(job=job, stages=[stage], pipelines=[pipeline], steps=[st1])
    svc = _validation_service()
    with pytest.raises(ValidationError) as exc_info:
        svc.validate_job_graph(graph, skip_reference_checks=True)
    assert "cover_image" in str(exc_info.value) or "icon_image" in str(exc_info.value)
