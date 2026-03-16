"""Job, stage, pipeline, and step definitions for Phase 3 domain model."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class JobDefinition:
    """Top-level executable graph (canonical orchestration object)."""

    id: str
    owner_user_id: str
    display_name: str
    target_id: str
    status: str
    stage_ids: list[str]
    workspace_id: str | None = None
    visibility: str = "owner"
    default_run_settings: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class StageDefinition:
    """Sequential grouping within a job; pipelines inside run in parallel by default."""

    id: str
    job_id: str
    display_name: str
    sequence: int
    pipeline_ids: list[str]
    pipeline_run_mode: str = "parallel"


@dataclass
class PipelineDefinition:
    """Mid-level container within a stage; contains ordered steps that run sequentially."""

    id: str
    stage_id: str
    display_name: str
    sequence: int
    step_ids: list[str]
    purpose: str | None = None


@dataclass
class StepTemplate:
    """Platform-owned reusable step definition (catalog layer)."""

    id: str
    slug: str
    display_name: str
    step_kind: str
    description: str
    input_contract: dict[str, Any]
    output_contract: dict[str, Any]
    config_schema: dict[str, Any]
    runtime_binding: str
    category: str
    status: str
    owner_user_id: str | None = None
    workspace_id: str | None = None
    visibility: str = "platform"


@dataclass
class StepInstance:
    """Tenant-owned configured use of a step inside a pipeline."""

    id: str
    pipeline_id: str
    step_template_id: str
    display_name: str
    sequence: int
    input_bindings: dict[str, Any]
    config: dict[str, Any]
    failure_policy: str | None = None
