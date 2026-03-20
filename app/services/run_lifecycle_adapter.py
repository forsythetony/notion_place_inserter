"""Adapter that provides Supabase-style run lifecycle API over RunRepository.

Bridges the worker and locations route (which expect create_job, create_run,
update_job_status, etc.) with the RunRepository protocol (save_job_run, etc.).
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger

from app.domain.runs import JobRun
from app.repositories.yaml_run_repository import YamlRunRepository, _find_job_run_by_id
from app.services.trigger_request_body import (
    build_trigger_payload,
    default_keywords_request_body_schema,
    validate_request_body_against_schema,
)


class RunLifecycleAdapter:
    """Provides Supabase-style run lifecycle API using YamlRunRepository.

    Used by worker and locations route. Persists JobRun with definition_snapshot_ref,
    trigger_payload, status, timestamps, and error summary.
    """

    def __init__(self, run_repo: YamlRunRepository) -> None:
        self._repo = run_repo

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
        """Create platform job record. For YAML, defers to create_run when run_id is provided."""
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
        """Create pipeline run record. Persists JobRun with full metadata when owner provided."""
        if not owner_user_id:
            return
        if keywords:
            schema = default_keywords_request_body_schema()
            trigger_payload = build_trigger_payload(
                validate_request_body_against_schema({"keywords": keywords}, schema),
                schema,
            )
        else:
            trigger_payload = {}
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
            self._repo.save_job_run(run)
            logger.info(
                "run_lifecycle_job_run_created | run_id={} platform_job_id={} owner={} definition_snapshot_ref={}",
                run_id,
                job_id,
                owner_user_id,
                definition_snapshot_ref,
            )
        except Exception as e:
            logger.exception(
                "run_lifecycle_create_run_failed | run_id={} platform_job_id={} error={}",
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
        """Update job status. job_id is platform_job_id; looks up JobRun and updates."""
        run = self._get_job_run_by_platform_job_id(job_id)
        if not run:
            logger.warning(
                "run_lifecycle_update_job_status_no_run | platform_job_id={}",
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
            self._repo.save_job_run(run)
        except Exception as e:
            logger.exception(
                "run_lifecycle_update_job_status_failed | platform_job_id={} status={} error={}",
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
        """Increment retry count for job. job_id is platform_job_id."""
        run = self._get_job_run_by_platform_job_id(job_id)
        if not run:
            return
        run.retry_count = retry_count
        if error_message is not None:
            run.error_summary = error_message
        try:
            self._repo.save_job_run(run)
        except Exception as e:
            logger.exception(
                "run_lifecycle_increment_retry_failed | platform_job_id={} retry_count={} error={}",
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
        """Update run status and optional result, completed_at."""
        run = _find_job_run_by_id(self._repo, run_id)
        if not run:
            logger.warning(
                "run_lifecycle_update_run_no_run | run_id={}",
                run_id,
            )
            return
        if status is not None:
            run.status = status
        if completed_at is not None:
            run.completed_at = completed_at
        try:
            self._repo.save_job_run(run)
        except Exception as e:
            logger.exception(
                "run_lifecycle_update_run_failed | run_id={} status={} error={}",
                run_id,
                status,
                e,
            )
            raise

    def get_run_status(self, run_id: str) -> str | None:
        """Fetch run status by run_id. Scans tenant dirs if needed."""
        run = _find_job_run_by_id(self._repo, run_id)
        return run.status if run else None

    def get_job_retry_count(self, job_id: str) -> int:
        """Fetch retry_count for platform job. Returns 0 if not found."""
        run = self._get_job_run_by_platform_job_id(job_id)
        return run.retry_count if run else 0

    def insert_event(
        self,
        run_id: str,
        event_type: str,
        event_payload_json: dict | None = None,
    ) -> None:
        """Insert event. For YAML we do not persist events separately; they are implicit in status."""
        logger.debug(
            "run_lifecycle_event | run_id={} event_type={}",
            run_id,
            event_type,
        )

    def _get_job_run_by_platform_job_id(self, platform_job_id: str) -> JobRun | None:
        """Find JobRun by platform_job_id by scanning owners."""
        owners = self._all_owners()
        for owner in owners:
            run = self._repo.get_job_run_by_platform_job_id(platform_job_id, owner)
            if run:
                return run
        return None

    def _all_owners(self) -> list[str]:
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent.parent
        tenants = root / "product_model" / "tenants"
        if not tenants.exists():
            return []
        return [d.name for d in tenants.iterdir() if d.is_dir()]
