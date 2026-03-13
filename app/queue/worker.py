"""Supabase-backed queue consumer and worker loop for location processing."""

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from loguru import logger

from app.queue.events import EventBus
from app.queue.models import PipelineFailureEvent, PipelineSuccessEvent
from app.services.supabase_queue_repository import QueueMessage, SupabaseQueueRepository
from app.services.supabase_run_repository import SupabaseRunRepository

if TYPE_CHECKING:
    from app.services.places_service import PlacesService

# Terminal statuses for idempotency; run already completed
_TERMINAL_STATUSES = frozenset({"succeeded", "failed"})

# Default visibility timeout (seconds) - pipeline can take several minutes
_DEFAULT_VT_SECONDS = 300

# Default poll interval when queue is empty
_DEFAULT_POLL_INTERVAL_SECONDS = 1.0


def _run_pipeline_sync(places_service: "PlacesService", keywords: str) -> dict:
    """Run the synchronous pipeline (call from worker thread)."""
    return places_service.create_place_from_query(keywords)


def _normalize_error(error: BaseException) -> str:
    """Produce a normalized error message for UI/history use."""
    msg = str(error).strip() or type(error).__name__
    return msg[:500] if len(msg) > 500 else msg


def _extract_payload(msg: QueueMessage) -> tuple[str, str, str, str | None] | None:
    """
    Extract job_id, run_id, keywords, recipient_whatsapp from message payload.
    Returns None if payload is malformed.
    """
    p = msg.payload or {}
    job_id = p.get("job_id")
    run_id = p.get("run_id")
    keywords = p.get("keywords")
    if not job_id or not run_id or keywords is None:
        return None
    recipient = p.get("recipient_whatsapp")
    return str(job_id), str(run_id), str(keywords).strip(), (
        str(recipient) if recipient else None
    )


async def run_worker_loop(
    queue_repo: SupabaseQueueRepository,
    run_repo: SupabaseRunRepository,
    places_service: "PlacesService",
    event_bus: EventBus,
    *,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
    vt_seconds: int = _DEFAULT_VT_SECONDS,
) -> None:
    """
    Consume messages from Supabase queue and run the pipeline.
    Persists lifecycle transitions (queued -> running -> succeeded/failed) and events.
    Runs until cancelled; use asyncio.create_task and cancel on shutdown.
    """
    loop = asyncio.get_event_loop()
    while True:
        try:
            messages = queue_repo.read(batch_size=1, vt_seconds=vt_seconds)
        except Exception:
            logger.exception("worker_queue_read_failed")
            await asyncio.sleep(poll_interval_seconds)
            continue

        if not messages:
            await asyncio.sleep(poll_interval_seconds)
            continue

        for msg in messages:
            try:
                await _process_message(
                    msg, queue_repo, run_repo, places_service, event_bus, loop
                )
            except Exception as e:
                logger.exception(
                    "worker_process_message_failed | msg_id={} error={}",
                    msg.message_id,
                    e,
                )
                # Do not archive on unexpected error - message will reappear after vt
                # Log and continue to next message
                continue


async def _process_message(
    msg: QueueMessage,
    queue_repo: SupabaseQueueRepository,
    run_repo: SupabaseRunRepository,
    places_service: "PlacesService",
    event_bus: EventBus,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Process a single queue message: validate, idempotency check, execute, persist, archive."""
    extracted = _extract_payload(msg)
    if extracted is None:
        logger.warning(
            "worker_malformed_payload | msg_id={} payload_keys={}",
            msg.message_id,
            list((msg.payload or {}).keys()),
        )
        queue_repo.archive(msg.message_id)
        return

    job_id, run_id, keywords, recipient_whatsapp = extracted

    # Idempotency: skip if run already terminal
    try:
        current_status = run_repo.get_run_status(run_id)
    except Exception:
        logger.exception("worker_idempotency_check_failed | run_id={}", run_id)
        raise

    if current_status and current_status in _TERMINAL_STATUSES:
        logger.info(
            "worker_duplicate_skip | run_id={} job_id={} status={}",
            run_id,
            job_id,
            current_status,
        )
        queue_repo.archive(msg.message_id)
        return

    now = datetime.now(timezone.utc)

    # Persist running
    try:
        run_repo.update_job_status(
            job_id, "running", started_at=now
        )
        run_repo.update_run(run_id, status="running")
        run_repo.insert_event(run_id, "pipeline_started", {"keywords_preview": keywords[:80]})
    except Exception:
        logger.exception("worker_persist_running_failed | run_id={}", run_id)
        raise

    # Execute pipeline
    try:
        result = await loop.run_in_executor(
            None,
            lambda k=keywords: _run_pipeline_sync(places_service, k),
        )
    except Exception as e:
        err_msg = _normalize_error(e)
        logger.exception("Pipeline failed for job {}", job_id)
        try:
            run_repo.update_job_status(
                job_id, "failed", completed_at=now, error_message=err_msg
            )
            run_repo.update_run(run_id, status="failed", completed_at=now)
            run_repo.insert_event(
                run_id,
                "pipeline_failed",
                {"error": err_msg},
            )
        except Exception as persist_err:
            logger.exception(
                "worker_persist_failure_failed | run_id={}",
                run_id,
            )
            raise persist_err from e

        event_bus.publish_failure(
            PipelineFailureEvent(
                job_id=job_id,
                run_id=run_id,
                keywords=keywords,
                error=e,
                recipient_whatsapp=recipient_whatsapp,
            )
        )
        queue_repo.archive(msg.message_id)
        return

    # Success path
    result_meta: dict[str, Any] = {}
    if isinstance(result, dict):
        result_meta = {k: v for k, v in result.items() if k in ("id", "page_id", "mode", "database")}

    try:
        run_repo.update_job_status(job_id, "succeeded", completed_at=now)
        run_repo.update_run(
            run_id,
            status="succeeded",
            result_json=result_meta or result if isinstance(result, dict) else {},
            completed_at=now,
        )
        run_repo.insert_event(
            run_id,
            "pipeline_succeeded",
            {"result_preview": result_meta},
        )
    except Exception:
        logger.exception("worker_persist_success_failed | run_id={}", run_id)
        raise

    event_bus.publish_success(
        PipelineSuccessEvent(
            job_id=job_id,
            run_id=run_id,
            keywords=keywords,
            result=result if isinstance(result, dict) else {},
            recipient_whatsapp=recipient_whatsapp,
        )
    )
    queue_repo.archive(msg.message_id)
