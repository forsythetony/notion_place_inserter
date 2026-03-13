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


def _parse_retry_delays(raw: str) -> tuple[int, ...]:
    """Parse WORKER_RETRY_DELAYS_SECONDS (e.g. '5,30,60') into tuple of ints."""
    if not raw or not raw.strip():
        return (5, 30, 60)
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    result: list[int] = []
    for p in parts:
        try:
            v = int(p)
            if v < 0:
                v = 0
            result.append(v)
        except ValueError:
            continue
    return tuple(result) if result else (5, 30, 60)


async def run_worker_loop(
    queue_repo: SupabaseQueueRepository,
    run_repo: SupabaseRunRepository,
    places_service: "PlacesService",
    event_bus: EventBus,
    *,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
    vt_seconds: int = _DEFAULT_VT_SECONDS,
    retry_delays_seconds: tuple[int, ...] = (5, 30, 60),
) -> None:
    """
    Consume messages from Supabase queue and run the pipeline.
    Persists lifecycle transitions (queued -> running -> succeeded/failed) and events.
    Bounded retries with backoff; final failure marks job/run failed and archives message.
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
                    msg,
                    queue_repo,
                    run_repo,
                    places_service,
                    event_bus,
                    loop,
                    retry_delays_seconds=retry_delays_seconds,
                )
            except Exception as e:
                logger.exception(
                    "worker_process_message_failed | msg_id={} error={}",
                    msg.message_id,
                    e,
                )
                # Bounded retries exhausted or non-retriable: mark failed and archive
                _handle_final_failure(msg, queue_repo, run_repo, event_bus, e)


def _handle_final_failure(
    msg: QueueMessage,
    queue_repo: SupabaseQueueRepository,
    run_repo: SupabaseRunRepository,
    event_bus: EventBus,
    error: BaseException,
) -> None:
    """Best-effort: persist failed, emit event, archive. Called when _process_message raises."""
    extracted = _extract_payload(msg)
    if extracted is None:
        queue_repo.archive(msg.message_id)
        return
    job_id, run_id, keywords, recipient_whatsapp = extracted
    err_msg = _normalize_error(error)
    now = datetime.now(timezone.utc)
    try:
        run_repo.update_job_status(
            job_id, "failed", completed_at=now, error_message=err_msg
        )
        run_repo.update_run(run_id, status="failed", completed_at=now)
        run_repo.insert_event(run_id, "pipeline_failed", {"error": err_msg})
    except Exception:
        logger.exception(
            "worker_final_failure_persist_failed | job_id={} run_id={}",
            job_id,
            run_id,
        )
    try:
        event_bus.publish_failure(
            PipelineFailureEvent(
                job_id=job_id,
                run_id=run_id,
                keywords=keywords,
                error=error,
                recipient_whatsapp=recipient_whatsapp,
            )
        )
    except Exception:
        logger.exception("worker_final_failure_event_failed | job_id={}", job_id)
    try:
        queue_repo.archive(msg.message_id)
    except Exception:
        logger.exception("worker_final_failure_archive_failed | msg_id={}", msg.message_id)
        raise


async def _process_message(
    msg: QueueMessage,
    queue_repo: SupabaseQueueRepository,
    run_repo: SupabaseRunRepository,
    places_service: "PlacesService",
    event_bus: EventBus,
    loop: asyncio.AbstractEventLoop,
    *,
    retry_delays_seconds: tuple[int, ...] = (5, 30, 60),
) -> None:
    """Process a single queue message: validate, idempotency check, bounded retries, execute, persist, archive."""
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

    # Bounded retry loop
    retry_count = run_repo.get_job_retry_count(job_id)
    max_retries = len(retry_delays_seconds)

    while True:
        now = datetime.now(timezone.utc)
        try:
            # Persist running
            run_repo.update_job_status(
                job_id, "running", started_at=now, retry_count=retry_count
            )
            run_repo.update_run(run_id, status="running")
            run_repo.insert_event(
                run_id, "pipeline_started", {"keywords_preview": keywords[:80]}
            )
        except Exception:
            logger.exception(
                "worker_persist_running_failed | job_id={} run_id={}",
                job_id,
                run_id,
            )
            err = RuntimeError("persist running failed")
            new_retry_count = retry_count + 1
            if new_retry_count <= max_retries and _persist_retry_and_schedule(
                run_repo, job_id, run_id, new_retry_count, _normalize_error(err)
            ):
                delay = retry_delays_seconds[retry_count]
                logger.info(
                    "worker_retry_scheduled | job_id={} run_id={} retry_count={} delay_seconds={}",
                    job_id,
                    run_id,
                    new_retry_count,
                    delay,
                )
                await asyncio.sleep(delay)
                retry_count = new_retry_count
                continue
            _mark_failed_and_archive(
                msg,
                queue_repo,
                run_repo,
                event_bus,
                job_id,
                run_id,
                keywords,
                recipient_whatsapp,
                _normalize_error(err),
                datetime.now(timezone.utc),
                err,
            )
            return

        # Execute pipeline
        try:
            result = await loop.run_in_executor(
                None,
                lambda k=keywords: _run_pipeline_sync(places_service, k),
            )
        except Exception as e:
            err_msg = _normalize_error(e)
            logger.exception(
                "worker_pipeline_failed | job_id={} run_id={} error={} attempt={}",
                job_id,
                run_id,
                err_msg,
                retry_count + 1,
            )
            new_retry_count = retry_count + 1
            if new_retry_count <= max_retries and _persist_retry_and_schedule(
                run_repo, job_id, run_id, new_retry_count, err_msg
            ):
                delay = retry_delays_seconds[retry_count]
                logger.info(
                    "worker_retry_scheduled | job_id={} run_id={} retry_count={} delay_seconds={}",
                    job_id,
                    run_id,
                    new_retry_count,
                    delay,
                )
                await asyncio.sleep(delay)
                retry_count = new_retry_count
                continue
            _mark_failed_and_archive(
                msg,
                queue_repo,
                run_repo,
                event_bus,
                job_id,
                run_id,
                keywords,
                recipient_whatsapp,
                err_msg,
                datetime.now(timezone.utc),
                e,
            )
            return

        # Success path
        result_meta: dict[str, Any] = {}
        if isinstance(result, dict):
            result_meta = {
                k: v
                for k, v in result.items()
                if k in ("id", "page_id", "mode", "database")
            }
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
            logger.exception(
                "worker_persist_success_failed | job_id={} run_id={}",
                job_id,
                run_id,
            )
            err = RuntimeError("persist success failed")
            new_retry_count = retry_count + 1
            if new_retry_count <= max_retries and _persist_retry_and_schedule(
                run_repo, job_id, run_id, new_retry_count, _normalize_error(err)
            ):
                delay = retry_delays_seconds[retry_count]
                logger.info(
                    "worker_retry_scheduled | job_id={} run_id={} retry_count={} delay_seconds={}",
                    job_id,
                    run_id,
                    new_retry_count,
                    delay,
                )
                await asyncio.sleep(delay)
                retry_count = new_retry_count
                continue
            _mark_failed_and_archive(
                msg,
                queue_repo,
                run_repo,
                event_bus,
                job_id,
                run_id,
                keywords,
                recipient_whatsapp,
                _normalize_error(err),
                datetime.now(timezone.utc),
                err,
            )
            return

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
        return


def _persist_retry_and_schedule(
    run_repo: SupabaseRunRepository,
    job_id: str,
    run_id: str,
    new_retry_count: int,
    err_msg: str,
) -> bool:
    """Persist retry_count for next attempt. Returns True on success, False on failure."""
    try:
        run_repo.increment_job_retry_count(
            job_id, new_retry_count, error_message=err_msg
        )
        return True
    except Exception:
        logger.exception(
            "worker_increment_retry_failed | job_id={} retry_count={}",
            job_id,
            new_retry_count,
        )
        return False


def _mark_failed_and_archive(
    msg: QueueMessage,
    queue_repo: SupabaseQueueRepository,
    run_repo: SupabaseRunRepository,
    event_bus: EventBus,
    job_id: str,
    run_id: str,
    keywords: str,
    recipient_whatsapp: str | None,
    err_msg: str,
    now: datetime,
    error: BaseException,
) -> None:
    """Persist failed status, emit event, archive."""
    try:
        run_repo.update_job_status(
            job_id, "failed", completed_at=now, error_message=err_msg
        )
        run_repo.update_run(run_id, status="failed", completed_at=now)
        run_repo.insert_event(run_id, "pipeline_failed", {"error": err_msg})
    except Exception:
        logger.exception(
            "worker_persist_failure_failed | job_id={} run_id={}",
            job_id,
            run_id,
        )
        raise
    event_bus.publish_failure(
        PipelineFailureEvent(
            job_id=job_id,
            run_id=run_id,
            keywords=keywords,
            error=error,
            recipient_whatsapp=recipient_whatsapp,
        )
    )
    queue_repo.archive(msg.message_id)
