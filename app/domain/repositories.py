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

    async def get_by_id(self, id: str) -> ConnectorTemplate | None: ...
    async def list_all(self) -> list[ConnectorTemplate]: ...
    async def save(self, template: ConnectorTemplate) -> None: ...
    async def delete(self, id: str) -> None: ...


@runtime_checkable
class ConnectorInstanceRepository(Protocol):
    """Repository for owner-scoped connector instances."""

    async def get_by_id(self, id: str, owner_user_id: str) -> ConnectorInstance | None: ...
    async def list_by_owner(self, owner_user_id: str) -> list[ConnectorInstance]: ...
    async def save(self, instance: ConnectorInstance) -> None: ...
    async def delete(self, id: str, owner_user_id: str) -> None: ...


@runtime_checkable
class TargetTemplateRepository(Protocol):
    """Repository for platform-owned target templates (catalog)."""

    async def get_by_id(self, id: str) -> TargetTemplate | None: ...
    async def list_all(self) -> list[TargetTemplate]: ...
    async def save(self, template: TargetTemplate) -> None: ...
    async def delete(self, id: str) -> None: ...


@runtime_checkable
class TargetRepository(Protocol):
    """Repository for owner-scoped data targets."""

    async def get_by_id(self, id: str, owner_user_id: str) -> DataTarget | None: ...
    async def list_by_owner(self, owner_user_id: str) -> list[DataTarget]: ...
    async def save(self, target: DataTarget) -> None: ...
    async def delete(self, id: str, owner_user_id: str) -> None: ...


@runtime_checkable
class TargetSchemaRepository(Protocol):
    """Repository for owner-scoped target schema snapshots."""

    async def get_by_id(
        self, id: str, owner_user_id: str
    ) -> TargetSchemaSnapshot | None: ...
    async def list_by_owner(
        self, owner_user_id: str
    ) -> list[TargetSchemaSnapshot]: ...
    async def get_active_for_target(
        self, data_target_id: str, owner_user_id: str
    ) -> TargetSchemaSnapshot | None: ...
    async def save(self, snapshot: TargetSchemaSnapshot) -> None: ...
    async def delete(self, id: str, owner_user_id: str) -> None: ...


@runtime_checkable
class TriggerRepository(Protocol):
    """Repository for owner-scoped trigger definitions."""

    async def get_by_id(
        self, id: str, owner_user_id: str
    ) -> TriggerDefinition | None: ...
    async def get_by_path(
        self, path: str, owner_user_id: str
    ) -> TriggerDefinition | None: ...
    async def list_by_owner(self, owner_user_id: str) -> list[TriggerDefinition]: ...
    async def save(self, trigger: TriggerDefinition) -> None: ...
    async def delete(self, id: str, owner_user_id: str) -> None: ...


@runtime_checkable
class TriggerJobLinkRepository(Protocol):
    """Repository for many-to-many trigger-job associations."""

    async def list_job_ids_for_trigger(
        self, trigger_id: str, owner_user_id: str
    ) -> list[str]: ...
    async def list_dispatchable_job_ids_for_trigger(
        self, trigger_id: str, owner_user_id: str
    ) -> list[str]:
        """
        Job IDs linked to this trigger that may run from a trigger invocation.
        Only ``active`` jobs; preserves order from ``list_job_ids_for_trigger``.
        """
        ...
    async def list_trigger_ids_for_job(
        self, job_id: str, owner_user_id: str
    ) -> list[str]: ...
    async def attach(self, trigger_id: str, job_id: str, owner_user_id: str) -> None: ...
    async def detach(self, trigger_id: str, job_id: str, owner_user_id: str) -> None: ...


@runtime_checkable
class JobRepository(Protocol):
    """Repository for owner-scoped job definitions."""

    async def get_by_id(
        self, id: str, owner_user_id: str
    ) -> JobDefinition | None: ...
    async def get_bootstrap_job(self, job_slug: str) -> JobDefinition | None: ...
    async def get_graph_by_id(self, id: str, owner_user_id: str) -> JobGraph | None: ...
    async def list_by_owner(self, owner_user_id: str) -> list[JobDefinition]: ...
    async def save(self, job: JobDefinition) -> None: ...
    async def update_job_status(self, id: str, owner_user_id: str, status: str) -> None: ...
    async def archive(self, id: str, owner_user_id: str) -> None: ...
    async def delete(self, id: str, owner_user_id: str) -> None: ...


@runtime_checkable
class StepTemplateRepository(Protocol):
    """Repository for platform-owned step templates (catalog)."""

    async def get_by_id(self, id: str) -> StepTemplate | None: ...
    async def list_all(self) -> list[StepTemplate]: ...
    async def save(self, template: StepTemplate) -> None: ...
    async def delete(self, id: str) -> None: ...


@runtime_checkable
class RunRepository(Protocol):
    """Repository for job runs and nested run records."""

    async def get_job_run(
        self, id: str, owner_user_id: str
    ) -> JobRun | None: ...
    async def get_job_run_by_platform_job_id(
        self, platform_job_id: str, owner_user_id: str
    ) -> JobRun | None: ...
    async def list_job_runs_by_owner(
        self,
        owner_user_id: str,
        *,
        job_id: str | None = None,
        limit: int = 100,
        from_iso: str | None = None,
        to_iso: str | None = None,
        offset: int = 0,
    ) -> list[JobRun]: ...
    async def list_recent_job_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        from_iso: str | None = None,
        to_iso: str | None = None,
        owner_user_ids: list[str] | None = None,
    ) -> list[JobRun]: ...
    async def save_job_run(self, run: JobRun) -> None: ...
    async def save_stage_run(self, run: StageRun) -> None: ...
    async def save_pipeline_run(self, run: PipelineRun) -> None: ...
    async def save_step_run(self, run: StepRun) -> None: ...
    async def list_step_runs_for_job_run(
        self, job_run_id: str, owner_user_id: str
    ) -> list[StepRun]: ...
    async def save_usage_record(self, record: UsageRecord) -> None: ...


@runtime_checkable
class AppConfigRepository(Protocol):
    """Repository for owner-scoped app config (limits, tenant settings)."""

    async def get_by_owner(self, owner_user_id: str) -> AppLimits | None: ...
    async def save(self, owner_user_id: str, limits: AppLimits) -> None: ...
