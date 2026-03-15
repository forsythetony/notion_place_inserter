"""Run and usage records for Phase 3 domain model."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class JobRun:
    """Record of a single job execution."""

    id: str
    owner_user_id: str
    job_id: str
    trigger_id: str
    target_id: str
    status: str
    trigger_payload: dict[str, Any]
    workspace_id: str | None = None
    visibility: str = "owner"
    definition_snapshot_ref: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_summary: str | None = None
    platform_job_id: str | None = None
    retry_count: int = 0


@dataclass
class StageRun:
    """Record of a single stage execution within a job run."""

    id: str
    job_run_id: str
    stage_id: str
    status: str
    owner_user_id: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class PipelineRun:
    """Record of a single pipeline execution within a stage run."""

    id: str
    stage_run_id: str
    pipeline_id: str
    status: str
    owner_user_id: str = ""
    job_run_id: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class StepRun:
    """Record of a single step execution within a pipeline run."""

    id: str
    pipeline_run_id: str
    step_id: str
    step_template_id: str
    status: str
    owner_user_id: str = ""
    job_run_id: str = ""
    stage_run_id: str = ""
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_summary: str | None = None


@dataclass
class UsageRecord:
    """Usage/accounting record (e.g. LLM tokens, external API calls)."""

    id: str
    job_run_id: str
    usage_type: str
    provider: str
    metric_name: str
    metric_value: float | int
    owner_user_id: str = ""
    step_run_id: str | None = None
    metadata: dict[str, Any] | None = None
