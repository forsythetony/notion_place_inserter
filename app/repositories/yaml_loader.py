"""Shared YAML loader and parser for Phase 3 domain model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.domain.connectors import ConnectorInstance, ConnectorTemplate
from app.domain.jobs import (
    JobDefinition,
    PipelineDefinition,
    StageDefinition,
    StepInstance,
    StepTemplate,
)
from app.domain.limits import AppLimits
from app.domain.targets import (
    DataTarget,
    TargetSchemaProperty,
    TargetSchemaSnapshot,
    TargetTemplate,
)
from app.domain.triggers import TriggerDefinition

from app.services.validation_service import JobGraph


def _project_root() -> Path:
    """Project root (parent of app/)."""
    return Path(__file__).resolve().parent.parent.parent


def _serialize_for_yaml(obj: Any) -> Any:
    """Recursively serialize values for YAML dump (e.g. datetime -> str)."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize_for_yaml(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize_for_yaml(x) for x in obj]
    return obj


def domain_to_yaml_dict(obj: Any) -> dict[str, Any]:
    """Convert a dataclass domain object to a dict suitable for YAML dump."""
    from dataclasses import asdict

    d = asdict(obj)
    return {k: _serialize_for_yaml(v) for k, v in d.items() if v is not None}


def dump_yaml_file(relative_path: str, data: dict[str, Any]) -> None:
    """Write dict to YAML file. Creates parent dirs if needed."""
    root = _project_root()
    full_path = root / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def load_yaml_file(relative_path: str) -> dict[str, Any] | None:
    """
    Load a YAML file from the product model tree.
    Path is relative to project root (e.g. product_model/catalog/connector_templates/foo.yaml).
    Returns None if file does not exist or cannot be parsed.
    """
    root = _project_root()
    full_path = root / relative_path
    if not full_path.exists() or not full_path.is_file():
        return None
    try:
        with open(full_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else None
    except (yaml.YAMLError, OSError):
        return None


def parse_trigger_definition(data: dict[str, Any]) -> TriggerDefinition:
    """Parse YAML dict into TriggerDefinition.
    secret_value/secret_last_rotated_at come from DB or are set by provisioning.
    """
    from datetime import datetime, timezone

    secret_val = data.get("secret_value", "")
    secret_rotated = data.get("secret_last_rotated_at")
    if isinstance(secret_rotated, str):
        try:
            secret_rotated = datetime.fromisoformat(secret_rotated.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            secret_rotated = None
    elif secret_rotated is None and secret_val:
        secret_rotated = datetime.now(timezone.utc)

    return TriggerDefinition(
        id=data["id"],
        owner_user_id=data["owner_user_id"],
        trigger_type=data["trigger_type"],
        display_name=data["display_name"],
        path=data["path"],
        method=data["method"],
        request_body_schema=data.get("request_body_schema", {}),
        status=data.get("status", "active"),
        auth_mode=data.get("auth_mode", "bearer"),
        secret_value=secret_val,
        secret_last_rotated_at=secret_rotated,
        workspace_id=data.get("workspace_id"),
        visibility=data.get("visibility", "owner"),
        created_at=None,
        updated_at=None,
    )


def parse_data_target(data: dict[str, Any]) -> DataTarget:
    """Parse YAML dict into DataTarget."""
    return DataTarget(
        id=data["id"],
        owner_user_id=data["owner_user_id"],
        target_template_id=data["target_template_id"],
        connector_instance_id=data["connector_instance_id"],
        display_name=data["display_name"],
        external_target_id=data["external_target_id"],
        status=data.get("status", "active"),
        workspace_id=data.get("workspace_id"),
        visibility=data.get("visibility", "owner"),
        active_schema_snapshot_id=data.get("active_schema_snapshot_id"),
        target_settings=data.get("target_settings"),
        property_rules=data.get("property_rules"),
        created_at=None,
        updated_at=None,
    )


def parse_target_schema_property(data: dict[str, Any]) -> TargetSchemaProperty:
    """Parse YAML dict into TargetSchemaProperty."""
    return TargetSchemaProperty(
        id=data["id"],
        external_property_id=data["external_property_id"],
        name=data["name"],
        normalized_slug=data.get("normalized_slug", data["name"].lower().replace(" ", "_")),
        property_type=data["property_type"],
        required=data.get("required", False),
        readonly=data.get("readonly", False),
        options=data.get("options"),
        metadata=data.get("metadata"),
    )


def parse_target_schema_snapshot(data: dict[str, Any]) -> TargetSchemaSnapshot:
    """Parse YAML dict into TargetSchemaSnapshot. Requires datetime for fetched_at."""
    from datetime import datetime, timezone

    fetched = data.get("fetched_at")
    if isinstance(fetched, str):
        fetched = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
    elif fetched is None:
        fetched = datetime.now(timezone.utc)
    props = data.get("properties") or []
    return TargetSchemaSnapshot(
        id=data["id"],
        owner_user_id=data["owner_user_id"],
        data_target_id=data["data_target_id"],
        version=data.get("version", "1"),
        fetched_at=fetched,
        is_active=data.get("is_active", True),
        source_connector_instance_id=data["source_connector_instance_id"],
        properties=[parse_target_schema_property(p) for p in props if isinstance(p, dict) and "id" in p],
        workspace_id=data.get("workspace_id"),
        visibility=data.get("visibility", "owner"),
        raw_source_payload=data.get("raw_source_payload"),
    )


def parse_connector_instance(data: dict[str, Any]) -> ConnectorInstance:
    """Parse YAML dict into ConnectorInstance."""
    return ConnectorInstance(
        id=data["id"],
        owner_user_id=data["owner_user_id"],
        connector_template_id=data["connector_template_id"],
        display_name=data["display_name"],
        status=data.get("status", "active"),
        config=data.get("config", {}),
        secret_ref=data.get("secret_ref"),
        workspace_id=data.get("workspace_id"),
        visibility=data.get("visibility", "owner"),
        last_validated_at=None,
        last_error=data.get("last_error"),
    )


def parse_app_limits(data: dict[str, Any]) -> AppLimits:
    """Parse YAML dict into AppLimits.

    Defaults are used when keys are missing. These will eventually come from
    backend configuration for easy tuning and frontend display.
    """
    return AppLimits(
        max_stages_per_job=data.get("max_stages_per_job", 20),
        max_pipelines_per_stage=data.get("max_pipelines_per_stage", 20),
        max_steps_per_pipeline=data.get("max_steps_per_pipeline", 50),
    )


def parse_connector_template(data: dict[str, Any]) -> ConnectorTemplate:
    """Parse YAML dict into ConnectorTemplate."""
    return ConnectorTemplate(
        id=data["id"],
        slug=data.get("slug", data["id"]),
        display_name=data["display_name"],
        connector_type=data["connector_type"],
        provider=data["provider"],
        auth_strategy=data["auth_strategy"],
        capabilities=data.get("capabilities", []),
        config_schema=data.get("config_schema", {}),
        secret_schema=data.get("secret_schema", {}),
        status=data.get("status", "active"),
        owner_user_id=data.get("owner_user_id"),
        workspace_id=data.get("workspace_id"),
        visibility=data.get("visibility", "platform"),
    )


def parse_target_template(data: dict[str, Any]) -> TargetTemplate:
    """Parse YAML dict into TargetTemplate."""
    return TargetTemplate(
        id=data["id"],
        slug=data.get("slug", data["id"]),
        display_name=data["display_name"],
        target_kind=data["target_kind"],
        required_connector_template_id=data["required_connector_template_id"],
        supports_schema_snapshots=data.get("supports_schema_snapshots", True),
        property_types_supported=data.get("property_types_supported", []),
        owner_user_id=data.get("owner_user_id"),
        workspace_id=data.get("workspace_id"),
        visibility=data.get("visibility", "platform"),
    )


def parse_step_template(data: dict[str, Any]) -> StepTemplate:
    """Parse YAML dict into StepTemplate."""
    return StepTemplate(
        id=data["id"],
        slug=data.get("slug", data["id"]),
        display_name=data["display_name"],
        step_kind=data["step_kind"],
        description=data.get("description", ""),
        input_contract=data.get("input_contract", {}),
        output_contract=data.get("output_contract", {}),
        config_schema=data.get("config_schema", {}),
        runtime_binding=data.get("runtime_binding", ""),
        category=data.get("category", "transform"),
        status=data.get("status", "active"),
        owner_user_id=data.get("owner_user_id"),
        workspace_id=data.get("workspace_id"),
        visibility=data.get("visibility", "platform"),
        query_schema=data.get("query_schema"),
    )


def parse_job_definition(data: dict[str, Any], owner_user_id_override: str | None = None) -> JobDefinition:
    """
    Parse YAML dict into JobDefinition.
    Extracts stage_ids from nested stages. Uses owner_user_id_override for bootstrap jobs
    when materializing for a specific user (otherwise uses data.owner_user_id).
    """
    stages = data.get("stages") or []
    stage_ids = [s["id"] for s in stages if isinstance(s, dict) and "id" in s]
    owner = owner_user_id_override if owner_user_id_override is not None else data.get("owner_user_id", "bootstrap")
    return JobDefinition(
        id=data["id"],
        owner_user_id=owner,
        display_name=data["display_name"],
        target_id=data["target_id"],
        status=data.get("status", "active"),
        stage_ids=stage_ids,
        workspace_id=data.get("workspace_id"),
        visibility=data.get("visibility", "owner"),
        default_run_settings=data.get("default_run_settings"),
        created_at=None,
        updated_at=None,
    )


def parse_step_instance(data: dict[str, Any], pipeline_id: str) -> StepInstance:
    """Parse YAML step dict into StepInstance."""
    return StepInstance(
        id=data["id"],
        pipeline_id=pipeline_id,
        step_template_id=data["step_template_id"],
        display_name=data.get("display_name", data["id"]),
        sequence=data.get("sequence", 1),
        input_bindings=data.get("input_bindings", {}),
        config=data.get("config", {}),
        failure_policy=data.get("failure_policy"),
    )


def parse_pipeline_definition(data: dict[str, Any], stage_id: str) -> tuple[PipelineDefinition, list[StepInstance]]:
    """
    Parse YAML pipeline dict into PipelineDefinition and nested StepInstances.
    Returns (pipeline, steps).
    """
    steps_data = data.get("steps") or []
    step_ids = [s["id"] for s in steps_data if isinstance(s, dict) and "id" in s]
    pipeline = PipelineDefinition(
        id=data["id"],
        stage_id=stage_id,
        display_name=data.get("display_name", data["id"]),
        sequence=data.get("sequence", 1),
        step_ids=step_ids,
        purpose=data.get("purpose"),
    )
    steps = [
        parse_step_instance(s, pipeline.id)
        for s in steps_data
        if isinstance(s, dict) and "id" in s
    ]
    return pipeline, steps


def parse_stage_definition(data: dict[str, Any], job_id: str) -> tuple[StageDefinition, list[PipelineDefinition], list[StepInstance]]:
    """
    Parse YAML stage dict into StageDefinition and nested pipelines/steps.
    Returns (stage, pipelines, steps).
    """
    pipelines_data = data.get("pipelines") or []
    pipeline_ids = [p["id"] for p in pipelines_data if isinstance(p, dict) and "id" in p]
    stage = StageDefinition(
        id=data["id"],
        job_id=job_id,
        display_name=data.get("display_name", data["id"]),
        sequence=data.get("sequence", 1),
        pipeline_ids=pipeline_ids,
        pipeline_run_mode=data.get("pipeline_run_mode", "parallel"),
    )
    pipelines: list[PipelineDefinition] = []
    steps: list[StepInstance] = []
    for p in pipelines_data:
        if isinstance(p, dict) and "id" in p:
            pipe, pipe_steps = parse_pipeline_definition(p, stage.id)
            pipelines.append(pipe)
            steps.extend(pipe_steps)
    return stage, pipelines, steps


def parse_job_graph(data: dict[str, Any], owner_user_id_override: str | None = None) -> JobGraph:
    """
    Parse full job YAML into JobGraph (job + stages + pipelines + steps).
    Used for validation and resolution. Preserves backward compatibility with parse_job_definition.
    """
    job = parse_job_definition(data, owner_user_id_override)
    stages_data = data.get("stages") or []
    stages: list[StageDefinition] = []
    pipelines: list[PipelineDefinition] = []
    steps: list[StepInstance] = []
    for s in stages_data:
        if isinstance(s, dict) and "id" in s:
            stage, stage_pipes, stage_steps = parse_stage_definition(s, job.id)
            stages.append(stage)
            pipelines.extend(stage_pipes)
            steps.extend(stage_steps)
    return JobGraph(job=job, stages=stages, pipelines=pipelines, steps=steps)


def job_graph_to_yaml_dict(graph: JobGraph) -> dict[str, Any]:
    """Convert JobGraph to YAML-serializable dict matching bootstrap job format."""
    job = graph.job
    stages_data = []
    for stage in sorted(graph.stages, key=lambda s: s.sequence):
        pipelines_data = []
        for pipeline in sorted(
            [p for p in graph.pipelines if p.stage_id == stage.id],
            key=lambda p: p.sequence,
        ):
            steps_data = []
            for step in sorted(
                [s for s in graph.steps if s.pipeline_id == pipeline.id],
                key=lambda s: s.sequence,
            ):
                steps_data.append(domain_to_yaml_dict(step))
            pipelines_data.append({
                **domain_to_yaml_dict(pipeline),
                "steps": steps_data,
            })
        stages_data.append({
            **domain_to_yaml_dict(stage),
            "pipelines": pipelines_data,
        })
    result = domain_to_yaml_dict(job)
    result["kind"] = "job_definition"
    result["stages"] = stages_data
    return result


def _parse_datetime(val: Any) -> "datetime | None":
    """Parse datetime from ISO string. Returns None if invalid."""
    from datetime import datetime, timezone

    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return None


def parse_job_run(data: dict[str, Any]) -> "JobRun":
    """Parse YAML dict into JobRun."""
    from app.domain.runs import JobRun

    return JobRun(
        id=data["id"],
        owner_user_id=data["owner_user_id"],
        job_id=data["job_id"],
        trigger_id=data["trigger_id"],
        target_id=data["target_id"],
        status=data["status"],
        trigger_payload=data.get("trigger_payload", {}),
        workspace_id=data.get("workspace_id"),
        visibility=data.get("visibility", "owner"),
        definition_snapshot_ref=data.get("definition_snapshot_ref"),
        started_at=_parse_datetime(data.get("started_at")),
        completed_at=_parse_datetime(data.get("completed_at")),
        error_summary=data.get("error_summary"),
        platform_job_id=data.get("platform_job_id"),
        retry_count=data.get("retry_count", 0),
    )


def parse_stage_run(data: dict[str, Any]) -> "StageRun":
    """Parse YAML dict into StageRun."""
    from app.domain.runs import StageRun

    return StageRun(
        id=data["id"],
        job_run_id=data["job_run_id"],
        stage_id=data["stage_id"],
        status=data["status"],
        owner_user_id=data.get("owner_user_id", ""),
        started_at=_parse_datetime(data.get("started_at")),
        completed_at=_parse_datetime(data.get("completed_at")),
    )


def parse_pipeline_run(data: dict[str, Any]) -> "PipelineRun":
    """Parse YAML dict into PipelineRun."""
    from app.domain.runs import PipelineRun

    return PipelineRun(
        id=data["id"],
        stage_run_id=data["stage_run_id"],
        pipeline_id=data["pipeline_id"],
        status=data["status"],
        owner_user_id=data.get("owner_user_id", ""),
        job_run_id=data.get("job_run_id", ""),
        started_at=_parse_datetime(data.get("started_at")),
        completed_at=_parse_datetime(data.get("completed_at")),
    )


def parse_step_run(data: dict[str, Any]) -> "StepRun":
    """Parse YAML dict into StepRun."""
    from app.domain.runs import StepRun

    return StepRun(
        id=data["id"],
        pipeline_run_id=data["pipeline_run_id"],
        step_id=data["step_id"],
        step_template_id=data["step_template_id"],
        status=data["status"],
        owner_user_id=data.get("owner_user_id", ""),
        job_run_id=data.get("job_run_id", ""),
        stage_run_id=data.get("stage_run_id", ""),
        input_summary=data.get("input_summary"),
        output_summary=data.get("output_summary"),
        started_at=_parse_datetime(data.get("started_at")),
        completed_at=_parse_datetime(data.get("completed_at")),
        error_summary=data.get("error_summary"),
    )


def parse_usage_record(data: dict[str, Any]) -> "UsageRecord":
    """Parse YAML dict into UsageRecord."""
    from app.domain.runs import UsageRecord

    return UsageRecord(
        id=data["id"],
        job_run_id=data["job_run_id"],
        usage_type=data["usage_type"],
        provider=data["provider"],
        metric_name=data["metric_name"],
        metric_value=data["metric_value"],
        owner_user_id=data.get("owner_user_id", ""),
        step_run_id=data.get("step_run_id"),
        metadata=data.get("metadata"),
    )
