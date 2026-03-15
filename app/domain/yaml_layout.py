"""YAML repository layout constants and path helpers for Phase 3 product model.

Canonical on-disk structure (no I/O; pure path construction):

  product_model/
    bootstrap/
      jobs/
    catalog/
      connector_templates/
      target_templates/
      step_templates/
    tenants/
      <owner_user_id>/
        app_config.yaml
        connector_instances/
        targets/
        target_schema_snapshots/
        triggers/
        jobs/
        runs/
"""

from __future__ import annotations

# Root directory for product model YAML (relative to project root or configurable base)
PRODUCT_MODEL_ROOT = "product_model"

# Bootstrap: shared starter templates (read-only, bundled)
BOOTSTRAP_JOBS = f"{PRODUCT_MODEL_ROOT}/bootstrap/jobs"
BOOTSTRAP_TRIGGERS = f"{PRODUCT_MODEL_ROOT}/bootstrap/triggers"

# Catalog: platform-owned templates (read-only, bundled)
CATALOG_CONNECTOR_TEMPLATES = f"{PRODUCT_MODEL_ROOT}/catalog/connector_templates"
CATALOG_TARGET_TEMPLATES = f"{PRODUCT_MODEL_ROOT}/catalog/target_templates"
CATALOG_STEP_TEMPLATES = f"{PRODUCT_MODEL_ROOT}/catalog/step_templates"

# Tenant subdir names (under tenants/<owner_user_id>/)
TENANT_APP_CONFIG = "app_config.yaml"
TENANT_CONNECTOR_INSTANCES = "connector_instances"
TENANT_TARGETS = "targets"
TENANT_TARGET_SCHEMA_SNAPSHOTS = "target_schema_snapshots"
TENANT_TRIGGERS = "triggers"
TENANT_JOBS = "jobs"
TENANT_RUNS = "runs"


def tenant_root(owner_user_id: str, base: str = PRODUCT_MODEL_ROOT) -> str:
    """Path to tenant root: product_model/tenants/<owner_user_id>/."""
    return f"{base}/tenants/{owner_user_id}"


def tenant_app_config_path(owner_user_id: str, base: str = PRODUCT_MODEL_ROOT) -> str:
    """Path to tenant app_config.yaml."""
    return f"{tenant_root(owner_user_id, base)}/{TENANT_APP_CONFIG}"


def tenant_connector_instances_dir(
    owner_user_id: str, base: str = PRODUCT_MODEL_ROOT
) -> str:
    """Path to tenant connector_instances directory."""
    return f"{tenant_root(owner_user_id, base)}/{TENANT_CONNECTOR_INSTANCES}"


def tenant_targets_dir(owner_user_id: str, base: str = PRODUCT_MODEL_ROOT) -> str:
    """Path to tenant targets directory."""
    return f"{tenant_root(owner_user_id, base)}/{TENANT_TARGETS}"


def tenant_target_schema_snapshots_dir(
    owner_user_id: str, base: str = PRODUCT_MODEL_ROOT
) -> str:
    """Path to tenant target_schema_snapshots directory."""
    return f"{tenant_root(owner_user_id, base)}/{TENANT_TARGET_SCHEMA_SNAPSHOTS}"


def tenant_triggers_dir(owner_user_id: str, base: str = PRODUCT_MODEL_ROOT) -> str:
    """Path to tenant triggers directory."""
    return f"{tenant_root(owner_user_id, base)}/{TENANT_TRIGGERS}"


def tenant_jobs_dir(owner_user_id: str, base: str = PRODUCT_MODEL_ROOT) -> str:
    """Path to tenant jobs directory."""
    return f"{tenant_root(owner_user_id, base)}/{TENANT_JOBS}"


def tenant_runs_dir(owner_user_id: str, base: str = PRODUCT_MODEL_ROOT) -> str:
    """Path to tenant runs directory."""
    return f"{tenant_root(owner_user_id, base)}/{TENANT_RUNS}"


def bootstrap_job_path(job_slug: str, base: str = PRODUCT_MODEL_ROOT) -> str:
    """Path to a bootstrap job file: bootstrap/jobs/<slug>.yaml."""
    return f"{base}/bootstrap/jobs/{job_slug}.yaml"


def bootstrap_trigger_path(
    trigger_id: str, base: str = PRODUCT_MODEL_ROOT
) -> str:
    """Path to a bootstrap trigger file: bootstrap/triggers/<id>.yaml."""
    return f"{base}/bootstrap/triggers/{trigger_id}.yaml"


def catalog_connector_template_path(
    template_id: str, base: str = PRODUCT_MODEL_ROOT
) -> str:
    """Path to a catalog connector template file."""
    return f"{base}/catalog/connector_templates/{template_id}.yaml"


def catalog_target_template_path(
    template_id: str, base: str = PRODUCT_MODEL_ROOT
) -> str:
    """Path to a catalog target template file."""
    return f"{base}/catalog/target_templates/{template_id}.yaml"


def catalog_step_template_path(
    template_id: str, base: str = PRODUCT_MODEL_ROOT
) -> str:
    """Path to a catalog step template file."""
    return f"{base}/catalog/step_templates/{template_id}.yaml"


def tenant_trigger_path(
    owner_user_id: str, trigger_id: str, base: str = PRODUCT_MODEL_ROOT
) -> str:
    """Path to a tenant trigger file: tenants/<owner>/triggers/<id>.yaml."""
    return f"{tenant_triggers_dir(owner_user_id, base)}/{trigger_id}.yaml"


def tenant_target_path(
    owner_user_id: str, target_id: str, base: str = PRODUCT_MODEL_ROOT
) -> str:
    """Path to a tenant target file: tenants/<owner>/targets/<id>.yaml."""
    return f"{tenant_targets_dir(owner_user_id, base)}/{target_id}.yaml"


def tenant_target_schema_snapshot_path(
    owner_user_id: str, snapshot_id: str, base: str = PRODUCT_MODEL_ROOT
) -> str:
    """Path to a tenant schema snapshot: tenants/<owner>/target_schema_snapshots/<id>.yaml."""
    return f"{tenant_target_schema_snapshots_dir(owner_user_id, base)}/{snapshot_id}.yaml"


def tenant_connector_instance_path(
    owner_user_id: str, instance_id: str, base: str = PRODUCT_MODEL_ROOT
) -> str:
    """Path to a tenant connector instance: tenants/<owner>/connector_instances/<id>.yaml."""
    return f"{tenant_connector_instances_dir(owner_user_id, base)}/{instance_id}.yaml"


def tenant_job_path(
    owner_user_id: str, job_id: str, base: str = PRODUCT_MODEL_ROOT
) -> str:
    """Path to a tenant job file: tenants/<owner>/jobs/<id>.yaml."""
    return f"{tenant_jobs_dir(owner_user_id, base)}/{job_id}.yaml"


def tenant_job_run_path(
    owner_user_id: str, run_id: str, base: str = PRODUCT_MODEL_ROOT
) -> str:
    """Path to a job run file: tenants/<owner>/runs/<run_id>.yaml."""
    return f"{tenant_runs_dir(owner_user_id, base)}/{run_id}.yaml"


def tenant_stage_run_path(
    owner_user_id: str, job_run_id: str, stage_run_id: str, base: str = PRODUCT_MODEL_ROOT
) -> str:
    """Path to a stage run file: tenants/<owner>/runs/<job_run_id>/stages/<stage_run_id>.yaml."""
    return f"{tenant_runs_dir(owner_user_id, base)}/{job_run_id}/stages/{stage_run_id}.yaml"


def tenant_pipeline_run_path(
    owner_user_id: str,
    job_run_id: str,
    stage_run_id: str,
    pipeline_run_id: str,
    base: str = PRODUCT_MODEL_ROOT,
) -> str:
    """Path to a pipeline run file under stage run."""
    return f"{tenant_runs_dir(owner_user_id, base)}/{job_run_id}/stages/{stage_run_id}/pipelines/{pipeline_run_id}.yaml"


def tenant_step_run_path(
    owner_user_id: str,
    job_run_id: str,
    stage_run_id: str,
    pipeline_run_id: str,
    step_run_id: str,
    base: str = PRODUCT_MODEL_ROOT,
) -> str:
    """Path to a step run file under pipeline run."""
    return f"{tenant_runs_dir(owner_user_id, base)}/{job_run_id}/stages/{stage_run_id}/pipelines/{pipeline_run_id}/steps/{step_run_id}.yaml"


def tenant_usage_record_path(
    owner_user_id: str, job_run_id: str, record_id: str, base: str = PRODUCT_MODEL_ROOT
) -> str:
    """Path to a usage record file: tenants/<owner>/runs/<job_run_id>/usage/<record_id>.yaml."""
    return f"{tenant_runs_dir(owner_user_id, base)}/{job_run_id}/usage/{record_id}.yaml"
