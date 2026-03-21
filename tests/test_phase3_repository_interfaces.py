"""Tests for Phase 3 repository interfaces and YAML layout (p3_pr02)."""

import inspect

import pytest

from app.domain import (
    AppConfigRepository,
    BOOTSTRAP_JOBS,
    CATALOG_CONNECTOR_TEMPLATES,
    CATALOG_STEP_TEMPLATES,
    CATALOG_TARGET_TEMPLATES,
    ConnectorInstanceRepository,
    ConnectorTemplateRepository,
    JobRepository,
    PRODUCT_MODEL_ROOT,
    RunRepository,
    StepTemplateRepository,
    TargetRepository,
    TargetSchemaRepository,
    TargetTemplateRepository,
    TriggerRepository,
    bootstrap_job_path,
    catalog_connector_template_path,
    catalog_step_template_path,
    catalog_target_template_path,
    tenant_app_config_path,
    tenant_connector_instances_dir,
    tenant_jobs_dir,
    tenant_root,
    tenant_runs_dir,
    tenant_targets_dir,
    tenant_target_schema_snapshots_dir,
    tenant_triggers_dir,
)


def test_repository_protocols_importable():
    """All p3_pr02 repository protocols are importable from app.domain."""
    protocols = [
        ConnectorTemplateRepository,
        ConnectorInstanceRepository,
        TargetTemplateRepository,
        TargetRepository,
        TargetSchemaRepository,
        TriggerRepository,
        JobRepository,
        StepTemplateRepository,
        RunRepository,
        AppConfigRepository,
    ]
    for p in protocols:
        assert p is not None
        assert hasattr(p, "__protocol_attrs__") or "Protocol" in str(type(p))


def test_connector_template_repository_has_expected_methods():
    """ConnectorTemplateRepository defines get_by_id, list_all, save, delete."""
    expected = {"get_by_id", "list_all", "save", "delete"}
    methods = {m for m in dir(ConnectorTemplateRepository) if not m.startswith("_")}
    assert expected.issubset(methods), f"Missing methods: {expected - methods}"


def test_connector_instance_repository_has_expected_methods():
    """ConnectorInstanceRepository defines get_by_id, list_by_owner, save, delete."""
    expected = {"get_by_id", "list_by_owner", "save", "delete"}
    methods = {m for m in dir(ConnectorInstanceRepository) if not m.startswith("_")}
    assert expected.issubset(methods), f"Missing methods: {expected - methods}"


def test_target_template_repository_has_expected_methods():
    """TargetTemplateRepository defines get_by_id, list_all, save, delete."""
    expected = {"get_by_id", "list_all", "save", "delete"}
    methods = {m for m in dir(TargetTemplateRepository) if not m.startswith("_")}
    assert expected.issubset(methods), f"Missing methods: {expected - methods}"


def test_target_repository_has_expected_methods():
    """TargetRepository defines get_by_id, list_by_owner, save, delete."""
    expected = {"get_by_id", "list_by_owner", "save", "delete"}
    methods = {m for m in dir(TargetRepository) if not m.startswith("_")}
    assert expected.issubset(methods), f"Missing methods: {expected - methods}"


def test_target_schema_repository_has_expected_methods():
    """TargetSchemaRepository defines get_by_id, list_by_owner, get_active_for_target, save, delete."""
    expected = {"get_by_id", "list_by_owner", "get_active_for_target", "save", "delete"}
    methods = {m for m in dir(TargetSchemaRepository) if not m.startswith("_")}
    assert expected.issubset(methods), f"Missing methods: {expected - methods}"


def test_trigger_repository_has_expected_methods():
    """TriggerRepository defines get_by_id, get_by_path, list_by_owner, save, delete."""
    expected = {"get_by_id", "get_by_path", "list_by_owner", "save", "delete"}
    methods = {m for m in dir(TriggerRepository) if not m.startswith("_")}
    assert expected.issubset(methods), f"Missing methods: {expected - methods}"


def test_job_repository_has_expected_methods():
    """JobRepository defines get_by_id, get_bootstrap_job, list_by_owner, save, update_job_status, delete."""
    expected = {"get_by_id", "get_bootstrap_job", "list_by_owner", "save", "update_job_status", "delete"}
    methods = {m for m in dir(JobRepository) if not m.startswith("_")}
    assert expected.issubset(methods), f"Missing methods: {expected - methods}"


def test_step_template_repository_has_expected_methods():
    """StepTemplateRepository defines get_by_id, list_all, save, delete."""
    expected = {"get_by_id", "list_all", "save", "delete"}
    methods = {m for m in dir(StepTemplateRepository) if not m.startswith("_")}
    assert expected.issubset(methods), f"Missing methods: {expected - methods}"


def test_run_repository_has_expected_methods():
    """RunRepository defines job run and nested run save methods."""
    expected = {
        "get_job_run",
        "list_job_runs_by_owner",
        "save_job_run",
        "save_stage_run",
        "save_pipeline_run",
        "save_step_run",
        "list_step_runs_for_job_run",
        "save_usage_record",
    }
    methods = {m for m in dir(RunRepository) if not m.startswith("_")}
    assert expected.issubset(methods), f"Missing methods: {expected - methods}"


def test_app_config_repository_has_expected_methods():
    """AppConfigRepository defines get_by_owner, save."""
    expected = {"get_by_owner", "save"}
    methods = {m for m in dir(AppConfigRepository) if not m.startswith("_")}
    assert expected.issubset(methods), f"Missing methods: {expected - methods}"


def test_yaml_layout_constants_match_architecture():
    """YAML layout constants match architecture doc: bootstrap, catalog, tenants."""
    assert PRODUCT_MODEL_ROOT == "product_model"
    assert "bootstrap" in BOOTSTRAP_JOBS and "jobs" in BOOTSTRAP_JOBS
    assert "catalog" in CATALOG_CONNECTOR_TEMPLATES and "connector_templates" in CATALOG_CONNECTOR_TEMPLATES
    assert "catalog" in CATALOG_TARGET_TEMPLATES and "target_templates" in CATALOG_TARGET_TEMPLATES
    assert "catalog" in CATALOG_STEP_TEMPLATES and "step_templates" in CATALOG_STEP_TEMPLATES


def test_tenant_root_path():
    """tenant_root builds product_model/tenants/<owner_user_id>/."""
    path = tenant_root("user_123")
    assert path == "product_model/tenants/user_123"


def test_bootstrap_job_path():
    """bootstrap_job_path builds bootstrap/jobs/<slug>.yaml."""
    path = bootstrap_job_path("notion_place_inserter")
    assert path == "product_model/bootstrap/jobs/notion_place_inserter.yaml"


def test_tenant_subdir_paths():
    """Tenant subdir helpers build correct paths."""
    owner = "user_abc"
    assert "connector_instances" in tenant_connector_instances_dir(owner)
    assert "targets" in tenant_targets_dir(owner)
    assert "target_schema_snapshots" in tenant_target_schema_snapshots_dir(owner)
    assert "triggers" in tenant_triggers_dir(owner)
    assert "jobs" in tenant_jobs_dir(owner)
    assert "runs" in tenant_runs_dir(owner)
    assert "app_config.yaml" in tenant_app_config_path(owner)


def test_catalog_path_helpers():
    """Catalog path helpers build correct paths."""
    path = catalog_connector_template_path("notion_oauth_workspace")
    assert "connector_templates" in path and path.endswith(".yaml")
    path = catalog_target_template_path("notion_database")
    assert "target_templates" in path and path.endswith(".yaml")
    path = catalog_step_template_path("optimize_input_claude")
    assert "step_templates" in path and path.endswith(".yaml")


def test_domain_repositories_module_has_no_storage_dependencies():
    """app.domain.repositories imports without YAML, filesystem, Supabase, or Postgres."""
    import app.domain.repositories as mod

    source = inspect.getsource(mod)
    storage_keywords = ["import yaml", "import ruamel", "open(", "Path(", "supabase", "postgres", "psycopg"]
    for kw in storage_keywords:
        assert kw not in source.lower(), f"Repository module should not reference storage: {kw}"


def test_domain_yaml_layout_module_has_no_io():
    """app.domain.yaml_layout has no file I/O; only path string construction."""
    import app.domain.yaml_layout as mod

    source = inspect.getsource(mod)
    io_keywords = ["open(", "read(", "write(", "Path(", "os.path.exists", "pathlib"]
    for kw in io_keywords:
        assert kw not in source, f"yaml_layout should not perform I/O: {kw}"
