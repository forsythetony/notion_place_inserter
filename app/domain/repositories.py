"""Repository interfaces for Phase 3 domain model. Storage-agnostic protocols."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.domain.connectors import ConnectorInstance, ConnectorTemplate
    from app.domain.jobs import (
        JobDefinition,
        PipelineDefinition,
        StageDefinition,
        StepInstance,
        StepTemplate,
    )
    from app.services.validation_service import JobGraph
    from app.domain.limits import AppLimits
    from app.domain.runs import (
        JobRun,
        PipelineRun,
        StageRun,
        StepRun,
        UsageRecord,
    )
    from app.domain.targets import (
        DataTarget,
        TargetSchemaSnapshot,
        TargetTemplate,
    )
    from app.domain.triggers import TriggerDefinition


@runtime_checkable
class ConnectorTemplateRepository(Protocol):
    """Repository for platform-owned connector templates (catalog)."""

    def get_by_id(self, id: str) -> ConnectorTemplate | None: ...
    def list_all(self) -> list[ConnectorTemplate]: ...
    def save(self, template: ConnectorTemplate) -> None: ...
    def delete(self, id: str) -> None: ...


@runtime_checkable
class ConnectorInstanceRepository(Protocol):
    """Repository for owner-scoped connector instances."""

    def get_by_id(self, id: str, owner_user_id: str) -> ConnectorInstance | None: ...
    def list_by_owner(self, owner_user_id: str) -> list[ConnectorInstance]: ...
    def save(self, instance: ConnectorInstance) -> None: ...
    def delete(self, id: str, owner_user_id: str) -> None: ...


@runtime_checkable
class TargetTemplateRepository(Protocol):
    """Repository for platform-owned target templates (catalog)."""

    def get_by_id(self, id: str) -> TargetTemplate | None: ...
    def list_all(self) -> list[TargetTemplate]: ...
    def save(self, template: TargetTemplate) -> None: ...
    def delete(self, id: str) -> None: ...


@runtime_checkable
class TargetRepository(Protocol):
    """Repository for owner-scoped data targets."""

    def get_by_id(self, id: str, owner_user_id: str) -> DataTarget | None: ...
    def list_by_owner(self, owner_user_id: str) -> list[DataTarget]: ...
    def save(self, target: DataTarget) -> None: ...
    def delete(self, id: str, owner_user_id: str) -> None: ...


@runtime_checkable
class TargetSchemaRepository(Protocol):
    """Repository for owner-scoped target schema snapshots."""

    def get_by_id(
        self, id: str, owner_user_id: str
    ) -> TargetSchemaSnapshot | None: ...
    def list_by_owner(
        self, owner_user_id: str
    ) -> list[TargetSchemaSnapshot]: ...
    def get_active_for_target(
        self, data_target_id: str, owner_user_id: str
    ) -> TargetSchemaSnapshot | None: ...
    def save(self, snapshot: TargetSchemaSnapshot) -> None: ...
    def delete(self, id: str, owner_user_id: str) -> None: ...


@runtime_checkable
class TriggerRepository(Protocol):
    """Repository for owner-scoped trigger definitions."""

    def get_by_id(
        self, id: str, owner_user_id: str
    ) -> TriggerDefinition | None: ...
    def get_by_path(
        self, path: str, owner_user_id: str
    ) -> TriggerDefinition | None: ...
    def list_by_owner(self, owner_user_id: str) -> list[TriggerDefinition]: ...
    def save(self, trigger: TriggerDefinition) -> None: ...
    def delete(self, id: str, owner_user_id: str) -> None: ...


@runtime_checkable
class TriggerJobLinkRepository(Protocol):
    """Repository for many-to-many trigger-job associations."""

    def list_job_ids_for_trigger(
        self, trigger_id: str, owner_user_id: str
    ) -> list[str]: ...
    def list_trigger_ids_for_job(
        self, job_id: str, owner_user_id: str
    ) -> list[str]: ...
    def attach(self, trigger_id: str, job_id: str, owner_user_id: str) -> None: ...
    def detach(self, trigger_id: str, job_id: str, owner_user_id: str) -> None: ...


@runtime_checkable
class JobRepository(Protocol):
    """Repository for owner-scoped job definitions."""

    def get_by_id(
        self, id: str, owner_user_id: str
    ) -> JobDefinition | None: ...
    def get_bootstrap_job(self, job_slug: str) -> JobDefinition | None: ...
    def get_graph_by_id(self, id: str, owner_user_id: str) -> JobGraph | None: ...
    def list_by_owner(self, owner_user_id: str) -> list[JobDefinition]: ...
    def save(self, job: JobDefinition) -> None: ...
    def delete(self, id: str, owner_user_id: str) -> None: ...


@runtime_checkable
class StepTemplateRepository(Protocol):
    """Repository for platform-owned step templates (catalog)."""

    def get_by_id(self, id: str) -> StepTemplate | None: ...
    def list_all(self) -> list[StepTemplate]: ...
    def save(self, template: StepTemplate) -> None: ...
    def delete(self, id: str) -> None: ...


@runtime_checkable
class RunRepository(Protocol):
    """Repository for job runs and nested run records."""

    def get_job_run(
        self, id: str, owner_user_id: str
    ) -> JobRun | None: ...
    def get_job_run_by_platform_job_id(
        self, platform_job_id: str, owner_user_id: str
    ) -> JobRun | None: ...
    def list_job_runs_by_owner(
        self, owner_user_id: str, *, job_id: str | None = None, limit: int = 100
    ) -> list[JobRun]: ...
    def save_job_run(self, run: JobRun) -> None: ...
    def save_stage_run(self, run: StageRun) -> None: ...
    def save_pipeline_run(self, run: PipelineRun) -> None: ...
    def save_step_run(self, run: StepRun) -> None: ...
    def save_usage_record(self, record: UsageRecord) -> None: ...


@runtime_checkable
class AppConfigRepository(Protocol):
    """Repository for owner-scoped app config (limits, tenant settings)."""

    def get_by_owner(self, owner_user_id: str) -> AppLimits | None: ...
    def save(self, owner_user_id: str, limits: AppLimits) -> None: ...
