"""Job, run, and event persistence via Supabase tables."""

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from supabase import Client

from app.integrations.supabase_config import SupabaseConfig


class SupabaseRunRepository:
    """
    Repository for platform_jobs, pipeline_runs, pipeline_run_events.
    Thin persistence layer; easy to fake in unit tests.
    """

    def __init__(self, client: Client, config: SupabaseConfig) -> None:
        self._client = client
        self._config = config

    def create_job(
        self,
        job_id: str,
        keywords: str,
        status: str = "queued",
    ) -> None:
        """Insert a job into platform_jobs."""
        try:
            self._client.table(self._config.table_platform_jobs).insert(
                {
                    "job_id": job_id,
                    "keywords": keywords,
                    "status": status,
                }
            ).execute()
        except Exception:
            logger.exception(
                "supabase_create_job_failed | job_id={}",
                job_id,
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
    ) -> None:
        """Update job status and optional timestamps."""
        payload: dict[str, Any] = {"status": status}
        if started_at is not None:
            payload["started_at"] = started_at.isoformat()
        if completed_at is not None:
            payload["completed_at"] = completed_at.isoformat()
        if error_message is not None:
            payload["error_message"] = error_message

        try:
            self._client.table(self._config.table_platform_jobs).update(payload).eq(
                "job_id", job_id
            ).execute()
        except Exception:
            logger.exception(
                "supabase_update_job_status_failed | job_id={} status={}",
                job_id,
                status,
            )
            raise

    def create_run(
        self,
        job_id: str,
        run_id: str,
        status: str = "pending",
    ) -> None:
        """Insert a run into pipeline_runs."""
        try:
            self._client.table(self._config.table_pipeline_runs).insert(
                {
                    "job_id": job_id,
                    "run_id": run_id,
                    "status": status,
                }
            ).execute()
        except Exception:
            logger.exception(
                "supabase_create_run_failed | job_id={} run_id={}",
                job_id,
                run_id,
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
        """Update run status, result, and/or completed_at."""
        payload: dict[str, Any] = {}
        if status is not None:
            payload["status"] = status
        if result_json is not None:
            payload["result_json"] = result_json
        if completed_at is not None:
            payload["completed_at"] = completed_at.isoformat()

        if not payload:
            return

        try:
            self._client.table(self._config.table_pipeline_runs).update(payload).eq(
                "run_id", run_id
            ).execute()
        except Exception:
            logger.exception(
                "supabase_update_run_failed | run_id={}",
                run_id,
            )
            raise

    def get_run_status(self, run_id: str) -> str | None:
        """Fetch run status by run_id. Returns None if run not found."""
        try:
            resp = (
                self._client.table(self._config.table_pipeline_runs)
                .select("status")
                .eq("run_id", run_id)
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception("supabase_get_run_status_failed | run_id={}", run_id)
            raise

        data = resp.data
        if not data or (isinstance(data, list) and len(data) == 0):
            return None
        row = data[0] if isinstance(data, list) else data
        return str(row.get("status", "")) if isinstance(row, dict) else None

    def insert_event(
        self,
        run_id: str,
        event_type: str,
        event_payload_json: dict | None = None,
    ) -> None:
        """Insert an event into pipeline_run_events."""
        payload: dict[str, Any] = {
            "run_id": run_id,
            "event_type": event_type,
        }
        if event_payload_json is not None:
            payload["event_payload_json"] = event_payload_json

        try:
            self._client.table(self._config.table_pipeline_run_events).insert(
                payload
            ).execute()
        except Exception:
            logger.exception(
                "supabase_insert_event_failed | run_id={} event_type={}",
                run_id,
                event_type,
            )
            raise
