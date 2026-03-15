"""Postgres-backed run repository with lifecycle API and id_mappings registry."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from loguru import logger
from supabase import Client

from app.domain.runs import (
    JobRun,
    PipelineRun,
    StageRun,
    StepRun,
    UsageRecord,
)
from app.repositories.id_mapping import resolve_or_create_mapping
from app.repositories.postgres_repositories import _ensure_uuid

# Valid run statuses (matches run_status_enum in Phase 4 schema)
_VALID_RUN_STATUSES = frozenset({"pending", "running", "succeeded", "failed", "cancelled"})


def _validate_run_status(status: str) -> None:
    """Raise ValueError if status is not a valid run_status_enum value."""
    if status not in _VALID_RUN_STATUSES:
        raise ValueError(
            f"invalid run status '{status}'; must be one of {sorted(_VALID_RUN_STATUSES)}"
        )


def _parse_dt(val: Any) -> datetime | None:
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


def _row_to_job_run(row: dict[str, Any]) -> JobRun:
    return JobRun(
        id=str(row["id"]),
        owner_user_id=str(row["owner_user_id"]),
        job_id=row["job_id"],
        trigger_id=row["trigger_id"],
        target_id=row["target_id"],
        status=str(row["status"]),
        trigger_payload=row.get("trigger_payload") or {},
        definition_snapshot_ref=row.get("definition_snapshot_ref"),
        platform_job_id=row.get("platform_job_id"),
        retry_count=row.get("retry_count", 0),
        started_at=_parse_dt(row.get("started_at")),
        completed_at=_parse_dt(row.get("completed_at")),
        error_summary=row.get("error_summary"),
    )


class PostgresRunRepository:
    """
    Postgres-backed run repository. Implements RunRepository and lifecycle API
    (create_job, create_run, update_job_status, etc.) for worker/route compatibility.
    Uses id_mappings for nested run IDs (stage, pipeline, step, usage).
    """

    JOB_RUNS = "job_runs"
    STAGE_RUNS = "stage_runs"
    PIPELINE_RUNS = "pipeline_run_executions"
    STEP_RUNS = "step_runs"
    USAGE_RECORDS = "usage_records"

    def __init__(self, client: Client) -> None:
        self._client = client

    # ---- RunRepository protocol ----

    def get_job_run(self, id: str, owner_user_id: str) -> JobRun | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = (
                self._client.table(self.JOB_RUNS)
                .select("*")
                .eq("id", id)
                .eq("owner_user_id", uid)
                .limit(1)
                .execute()
            )
        except ValueError:
            return None
        except Exception as e:
            logger.exception("postgres_get_job_run_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_job_run(rows[0])

    def get_job_run_by_platform_job_id(
        self, platform_job_id: str, owner_user_id: str
    ) -> JobRun | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = (
                self._client.table(self.JOB_RUNS)
                .select("*")
                .eq("platform_job_id", platform_job_id)
                .eq("owner_user_id", uid)
                .limit(1)
                .execute()
            )
        except ValueError:
            return None
        except Exception as e:
            logger.exception(
                "postgres_get_job_run_by_platform_job_id_failed | platform_job_id={} error={}",
                platform_job_id,
                e,
            )
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_job_run(rows[0])

    def find_job_run_by_platform_job_id(self, platform_job_id: str) -> JobRun | None:
        """Find JobRun by platform_job_id without owner (for lifecycle adapter)."""
        try:
            r = (
                self._client.table(self.JOB_RUNS)
                .select("*")
                .eq("platform_job_id", platform_job_id)
                .limit(1)
                .execute()
            )
        except Exception as e:
            logger.exception(
                "postgres_find_job_run_by_platform_job_id_failed | platform_job_id={} error={}",
                platform_job_id,
                e,
            )
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_job_run(rows[0])

    def find_job_run_by_id(self, run_id: str) -> JobRun | None:
        """Find JobRun by id without owner (for lifecycle adapter)."""
        try:
            r = (
                self._client.table(self.JOB_RUNS)
                .select("*")
                .eq("id", run_id)
                .limit(1)
                .execute()
            )
        except Exception as e:
            logger.exception("postgres_find_job_run_by_id_failed | run_id={} error={}", run_id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_job_run(rows[0])

    def list_job_runs_by_owner(
        self,
        owner_user_id: str,
        *,
        job_id: str | None = None,
        limit: int = 100,
    ) -> list[JobRun]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            q = self._client.table(self.JOB_RUNS).select("*").eq("owner_user_id", uid)
            if job_id:
                q = q.eq("job_id", job_id)
            r = q.order("created_at", desc=True).limit(limit).execute()
        except ValueError:
            return []
        except Exception as e:
            logger.exception("postgres_list_job_runs_failed | owner={} error={}", owner_user_id, e)
            raise
        return [_row_to_job_run(row) for row in (r.data or [])]

    def save_job_run(self, run: JobRun) -> None:
        _validate_run_status(run.status)
        uid = str(_ensure_uuid(run.owner_user_id))
        row = {
            "id": run.id,
            "owner_user_id": uid,
            "job_id": run.job_id,
            "trigger_id": run.trigger_id,
            "target_id": run.target_id,
            "status": run.status,
            "trigger_payload": run.trigger_payload,
            "definition_snapshot_ref": run.definition_snapshot_ref,
            "platform_job_id": run.platform_job_id,
            "retry_count": run.retry_count,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "error_summary": run.error_summary,
        }
        try:
            self._client.table(self.JOB_RUNS).upsert(row, on_conflict="id").execute()
        except Exception as e:
            logger.exception("postgres_save_job_run_failed | run_id={} error={}", run.id, e)
            raise

    def save_stage_run(self, run: StageRun) -> None:
        _validate_run_status(run.status)
        uid = str(_ensure_uuid(run.owner_user_id))
        job_run_uuid = UUID(run.job_run_id)
        stage_run_uuid = resolve_or_create_mapping(
            self._client, "stage_run", run.id
        )
        row = {
            "id": str(stage_run_uuid),
            "job_run_id": str(job_run_uuid),
            "stage_id": run.stage_id,
            "owner_user_id": uid,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
        try:
            self._client.table(self.STAGE_RUNS).upsert(row, on_conflict="id").execute()
        except Exception as e:
            logger.exception("postgres_save_stage_run_failed | stage_run_id={} error={}", run.id, e)
            raise

    def save_pipeline_run(self, run: PipelineRun) -> None:
        _validate_run_status(run.status)
        uid = str(_ensure_uuid(run.owner_user_id))
        stage_run_uuid = resolve_or_create_mapping(
            self._client, "stage_run", run.stage_run_id
        )
        job_run_uuid = UUID(run.job_run_id)
        pipeline_run_uuid = resolve_or_create_mapping(
            self._client, "pipeline_run", run.id
        )
        row = {
            "id": str(pipeline_run_uuid),
            "stage_run_id": str(stage_run_uuid),
            "pipeline_id": run.pipeline_id,
            "job_run_id": str(job_run_uuid),
            "owner_user_id": uid,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
        try:
            self._client.table(self.PIPELINE_RUNS).upsert(row, on_conflict="id").execute()
        except Exception as e:
            logger.exception("postgres_save_pipeline_run_failed | pipeline_run_id={} error={}", run.id, e)
            raise

    def save_step_run(self, run: StepRun) -> None:
        _validate_run_status(run.status)
        uid = str(_ensure_uuid(run.owner_user_id))
        pipeline_run_uuid = resolve_or_create_mapping(
            self._client, "pipeline_run", run.pipeline_run_id
        )
        job_run_uuid = UUID(run.job_run_id)
        stage_run_uuid = resolve_or_create_mapping(
            self._client, "stage_run", run.stage_run_id
        )
        step_run_uuid = resolve_or_create_mapping(
            self._client, "step_run", run.id
        )
        row = {
            "id": str(step_run_uuid),
            "pipeline_run_id": str(pipeline_run_uuid),
            "step_id": run.step_id,
            "step_template_id": run.step_template_id,
            "job_run_id": str(job_run_uuid),
            "stage_run_id": str(stage_run_uuid),
            "owner_user_id": uid,
            "status": run.status,
            "input_summary": run.input_summary,
            "output_summary": run.output_summary,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "error_summary": run.error_summary,
        }
        try:
            self._client.table(self.STEP_RUNS).upsert(row, on_conflict="id").execute()
        except Exception as e:
            logger.exception("postgres_save_step_run_failed | step_run_id={} error={}", run.id, e)
            raise

    def save_usage_record(self, record: UsageRecord) -> None:
        uid = str(_ensure_uuid(record.owner_user_id))
        job_run_uuid = UUID(record.job_run_id)
        step_run_uuid = None
        if record.step_run_id:
            step_run_uuid = resolve_or_create_mapping(
                self._client, "step_run", record.step_run_id
            )
        usage_uuid = resolve_or_create_mapping(
            self._client, "usage_record", record.id
        )
        row = {
            "id": str(usage_uuid),
            "job_run_id": str(job_run_uuid),
            "owner_user_id": uid,
            "usage_type": record.usage_type,
            "provider": record.provider,
            "metric_name": record.metric_name,
            "metric_value": float(record.metric_value),
            "step_run_id": str(step_run_uuid) if step_run_uuid is not None else None,
            "metadata": record.metadata,
        }
        try:
            self._client.table(self.USAGE_RECORDS).insert(row).execute()
        except Exception as e:
            logger.exception("postgres_save_usage_record_failed | record_id={} error={}", record.id, e)
            raise

    # ---- Lifecycle API (worker/route) ----

    def create_job(
        self,
        job_id: str,
        keywords: str,
        status: str = "queued",
        *,
        owner_user_id: str | None = None,
        run_id: str | None = None,
        job_definition_id: str | None = None,
        trigger_id: str | None = None,
        target_id: str | None = None,
        definition_snapshot_ref: str | None = None,
    ) -> None:
        if run_id and owner_user_id:
            self.create_run(
                job_id=job_id,
                run_id=run_id,
                status="pending",
                owner_user_id=owner_user_id,
                keywords=keywords,
                job_definition_id=job_definition_id,
                trigger_id=trigger_id,
                target_id=target_id,
                definition_snapshot_ref=definition_snapshot_ref,
            )

    def create_run(
        self,
        job_id: str,
        run_id: str,
        status: str = "pending",
        *,
        owner_user_id: str | None = None,
        keywords: str | None = None,
        job_definition_id: str | None = None,
        trigger_id: str | None = None,
        target_id: str | None = None,
        definition_snapshot_ref: str | None = None,
    ) -> None:
        if not owner_user_id:
            return
        trigger_payload = {"raw_input": keywords} if keywords else {}
        run = JobRun(
            id=run_id,
            owner_user_id=owner_user_id,
            job_id=job_definition_id or job_id,
            trigger_id=trigger_id or "",
            target_id=target_id or "",
            status=status,
            trigger_payload=trigger_payload,
            definition_snapshot_ref=definition_snapshot_ref,
            platform_job_id=job_id,
            retry_count=0,
        )
        try:
            self.save_job_run(run)
            logger.info(
                "postgres_run_create_run | run_id={} platform_job_id={} owner={} definition_snapshot_ref={}",
                run_id,
                job_id,
                owner_user_id,
                definition_snapshot_ref,
            )
        except Exception as e:
            logger.exception(
                "postgres_run_create_run_failed | run_id={} platform_job_id={} error={}",
                run_id,
                job_id,
                e,
            )
            raise

    def update_job_status(
        self,
        job_id: str,
        status: str,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
        retry_count: int | None = None,
    ) -> None:
        run = self.find_job_run_by_platform_job_id(job_id)
        if not run:
            logger.warning(
                "postgres_run_update_job_status_no_run | platform_job_id={}",
                job_id,
            )
            return
        run.status = status
        if started_at is not None:
            run.started_at = started_at
        if completed_at is not None:
            run.completed_at = completed_at
        if error_message is not None:
            run.error_summary = error_message
        if retry_count is not None:
            run.retry_count = retry_count
        try:
            self.save_job_run(run)
        except Exception as e:
            logger.exception(
                "postgres_run_update_job_status_failed | platform_job_id={} status={} error={}",
                job_id,
                status,
                e,
            )
            raise

    def increment_job_retry_count(
        self,
        job_id: str,
        retry_count: int,
        *,
        error_message: str | None = None,
    ) -> None:
        run = self.find_job_run_by_platform_job_id(job_id)
        if not run:
            return
        run.retry_count = retry_count
        if error_message is not None:
            run.error_summary = error_message
        try:
            self.save_job_run(run)
        except Exception as e:
            logger.exception(
                "postgres_run_increment_retry_failed | platform_job_id={} retry_count={} error={}",
                job_id,
                retry_count,
                e,
            )
            raise

    def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        result_json: dict | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        run = self.find_job_run_by_id(run_id)
        if not run:
            logger.warning(
                "postgres_run_update_run_no_run | run_id={}",
                run_id,
            )
            return
        if status is not None:
            run.status = status
        if completed_at is not None:
            run.completed_at = completed_at
        try:
            self.save_job_run(run)
        except Exception as e:
            logger.exception(
                "postgres_run_update_run_failed | run_id={} status={} error={}",
                run_id,
                status,
                e,
            )
            raise

    def get_run_status(self, run_id: str) -> str | None:
        run = self.find_job_run_by_id(run_id)
        return run.status if run else None

    def get_job_retry_count(self, job_id: str) -> int:
        run = self.find_job_run_by_platform_job_id(job_id)
        return run.retry_count if run else 0

    def insert_event(
        self,
        run_id: str,
        event_type: str,
        event_payload_json: dict | None = None,
    ) -> None:
        # Phase 4: logs-only observability; events not persisted to DB.
        # Log at INFO for run correlation and debugging in datastore mode.
        payload_preview = (event_payload_json or {})
        logger.info(
            "postgres_run_event | run_id={} event_type={} payload={}",
            run_id,
            event_type,
            payload_preview,
        )


