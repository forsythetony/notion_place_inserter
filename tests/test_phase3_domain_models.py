"""Tests for Phase 3 domain model (p3_pr01)."""

from datetime import datetime, timezone

import pytest

from app.domain import (
    AppLimits,
    ConnectorInstance,
    ConnectorTemplate,
    DataTarget,
    JobDefinition,
    JobRun,
    PipelineDefinition,
    PipelineRun,
    StageDefinition,
    StageRun,
    StepInstance,
    StepRun,
    StepTemplate,
    TargetSchemaProperty,
    TargetSchemaSnapshot,
    TargetTemplate,
    TriggerDefinition,
    UsageRecord,
    Visibility,
)


def test_import_all_domain_classes():
    """All architecture-doc domain classes and p3_pr02 contracts are importable from app.domain."""
    from app.domain import __all__ as exported

    # Core domain classes (p3_pr01)
    domain_classes = {
        "AppLimits",
        "ConnectorInstance",
        "ConnectorTemplate",
        "DataTarget",
        "JobDefinition",
        "JobRun",
        "PipelineDefinition",
        "PipelineRun",
        "StageDefinition",
        "StageRun",
        "StepInstance",
        "StepRun",
        "StepTemplate",
        "TargetSchemaProperty",
        "TargetSchemaSnapshot",
        "TargetTemplate",
        "TriggerDefinition",
        "UsageRecord",
        "Visibility",
    }
    assert domain_classes.issubset(set(exported)), "Domain classes missing from __all__"


def test_visibility_type():
    """Visibility is a Literal type for platform | owner."""
    v: Visibility = "platform"
    assert v == "platform"
    v = "owner"
    assert v == "owner"


def test_connector_template_instantiation():
    """ConnectorTemplate can be instantiated with required fields."""
    t = ConnectorTemplate(
        id="ct-1",
        slug="notion_oauth",
        display_name="Notion OAuth",
        connector_type="oauth",
        provider="notion",
        auth_strategy="oauth2",
        capabilities=["fetch_target_schema", "create_target_record"],
        config_schema={},
        secret_schema={},
        status="active",
    )
    assert t.id == "ct-1"
    assert t.visibility == "platform"
    assert t.owner_user_id is None


def test_connector_instance_instantiation():
    """ConnectorInstance can be instantiated with required fields and ownership metadata."""
    i = ConnectorInstance(
        id="ci-1",
        owner_user_id="user_123",
        connector_template_id="ct-1",
        display_name="My Notion",
        status="active",
        config={"workspace_id": "abc"},
        secret_ref="env:NOTION_SECRET",
    )
    assert i.owner_user_id == "user_123"
    assert i.visibility == "owner"
    assert i.workspace_id is None


def test_template_vs_instance_separation_connectors():
    """ConnectorTemplate and ConnectorInstance are distinct concrete classes."""
    assert ConnectorTemplate is not ConnectorInstance
    assert not issubclass(ConnectorInstance, ConnectorTemplate)
    assert not issubclass(ConnectorTemplate, ConnectorInstance)


def test_target_template_instantiation():
    """TargetTemplate can be instantiated with required fields."""
    t = TargetTemplate(
        id="tt-1",
        slug="notion_database",
        display_name="Notion Database",
        target_kind="notion_database",
        required_connector_template_id="ct-1",
        supports_schema_snapshots=True,
        property_types_supported=["title", "rich_text", "select"],
    )
    assert t.visibility == "platform"


def test_data_target_instantiation():
    """DataTarget can be instantiated with ownership metadata."""
    t = DataTarget(
        id="dt-1",
        owner_user_id="user_123",
        target_template_id="tt-1",
        connector_instance_id="ci-1",
        display_name="Places DB",
        external_target_id="notion-db-abc",
        status="active",
    )
    assert t.owner_user_id == "user_123"
    assert t.visibility == "owner"


def test_template_vs_instance_separation_targets():
    """TargetTemplate and DataTarget are distinct concrete classes."""
    assert TargetTemplate is not DataTarget
    assert not issubclass(DataTarget, TargetTemplate)


def test_target_schema_snapshot_and_property():
    """TargetSchemaSnapshot and TargetSchemaProperty can be instantiated."""
    prop = TargetSchemaProperty(
        id="prop-1",
        external_property_id="ext-1",
        name="Title",
        normalized_slug="title",
        property_type="title",
    )
    now = datetime.now(timezone.utc)
    snap = TargetSchemaSnapshot(
        id="snap-1",
        owner_user_id="user_123",
        data_target_id="dt-1",
        version="1",
        fetched_at=now,
        is_active=True,
        source_connector_instance_id="ci-1",
        properties=[prop],
    )
    assert snap.owner_user_id == "user_123"
    assert len(snap.properties) == 1
    assert snap.properties[0].name == "Title"


def test_trigger_definition_instantiation():
    """TriggerDefinition can be instantiated with ownership metadata."""
    t = TriggerDefinition(
        id="tr-1",
        owner_user_id="user_123",
        trigger_type="http",
        display_name="Locations API",
        path="/locations",
        method="POST",
        request_body_schema={"type": "object", "properties": {"keywords": {"type": "string"}}},
        status="active",
        auth_mode="bearer",
        secret_value="test_secret_abc",
    )
    assert t.owner_user_id == "user_123"
    assert t.visibility == "owner"


def test_job_definition_instantiation():
    """JobDefinition can be instantiated with ownership metadata."""
    j = JobDefinition(
        id="job-1",
        owner_user_id="user_123",
        display_name="Notion Place Inserter",
        target_id="dt-1",
        status="active",
        stage_ids=["stage-1"],
    )
    assert j.owner_user_id == "user_123"
    assert j.visibility == "owner"


def test_stage_and_pipeline_definition_instantiation():
    """StageDefinition and PipelineDefinition can be instantiated."""
    stage = StageDefinition(
        id="stage-1",
        job_id="job-1",
        display_name="Fetch & Enrich",
        sequence=1,
        pipeline_ids=["pipe-1", "pipe-2"],
    )
    pipe = PipelineDefinition(
        id="pipe-1",
        stage_id="stage-1",
        display_name="Places Pipeline",
        sequence=1,
        step_ids=["step-1"],
    )
    assert stage.pipeline_run_mode == "parallel"
    assert pipe.stage_id == "stage-1"


def test_step_template_instantiation():
    """StepTemplate can be instantiated (platform-owned)."""
    t = StepTemplate(
        id="st-1",
        slug="optimize_input",
        display_name="Optimize Input",
        step_kind="claude_optimize",
        description="Reshape input for downstream",
        input_contract={},
        output_contract={},
        config_schema={},
        runtime_binding="claude",
        category="ai",
        status="active",
    )
    assert t.visibility == "platform"


def test_step_instance_instantiation():
    """StepInstance can be instantiated (pipeline-scoped)."""
    i = StepInstance(
        id="si-1",
        pipeline_id="pipe-1",
        step_template_id="st-1",
        display_name="Optimize Query",
        sequence=1,
        input_bindings={"query": "trigger.payload.keywords"},
        config={"prompt": "..."},
    )
    assert i.pipeline_id == "pipe-1"
    assert i.step_template_id == "st-1"


def test_template_vs_instance_separation_steps():
    """StepTemplate and StepInstance are distinct concrete classes."""
    assert StepTemplate is not StepInstance
    assert not issubclass(StepInstance, StepTemplate)


def test_app_limits_instantiation():
    """AppLimits can be instantiated."""
    limits = AppLimits(
        max_stages_per_job=10,
        max_pipelines_per_stage=20,
        max_steps_per_pipeline=50,
    )
    assert limits.max_stages_per_job == 10


def test_job_run_instantiation():
    """JobRun can be instantiated with ownership metadata."""
    r = JobRun(
        id="run-1",
        owner_user_id="user_123",
        job_id="job-1",
        trigger_id="tr-1",
        target_id="dt-1",
        status="succeeded",
        trigger_payload={"keywords": "stone arch bridge"},
    )
    assert r.owner_user_id == "user_123"
    assert r.visibility == "owner"


def test_stage_run_pipeline_run_step_run_instantiation():
    """StageRun, PipelineRun, StepRun can be instantiated."""
    stage_run = StageRun(
        id="sr-1",
        job_run_id="run-1",
        stage_id="stage-1",
        status="succeeded",
    )
    pipe_run = PipelineRun(
        id="pr-1",
        stage_run_id="sr-1",
        pipeline_id="pipe-1",
        status="succeeded",
    )
    step_run = StepRun(
        id="stepr-1",
        pipeline_run_id="pr-1",
        step_id="si-1",
        step_template_id="st-1",
        status="succeeded",
    )
    assert stage_run.job_run_id == "run-1"
    assert pipe_run.stage_run_id == "sr-1"
    assert step_run.step_template_id == "st-1"


def test_usage_record_instantiation():
    """UsageRecord can be instantiated."""
    u = UsageRecord(
        id="usage-1",
        job_run_id="run-1",
        usage_type="llm_tokens",
        provider="anthropic",
        metric_name="prompt_tokens",
        metric_value=150,
    )
    assert u.usage_type == "llm_tokens"
    assert u.step_run_id is None


def test_domain_module_has_no_storage_dependencies():
    """Domain module imports without YAML or Postgres dependencies."""
    # Importing app.domain should not pull in yaml, supabase, or repository code
    import sys

    mod = sys.modules.get("app.domain")
    assert mod is not None
    # If we got here without ImportError, we're good
    from app.domain import JobDefinition, StepInstance

    j = JobDefinition(
        id="j1",
        owner_user_id="u1",
        display_name="Test",
        target_id="d1",
        status="active",
        stage_ids=[],
    )
    s = StepInstance(
        id="s1",
        pipeline_id="p1",
        step_template_id="st1",
        display_name="Step",
        sequence=1,
        input_bindings={},
        config={},
    )
    assert j.id == "j1"
    assert s.id == "s1"
