"""Supabase-backed queue consumer and worker loop for location processing."""

import asyncio
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from loguru import logger

from app.queue.events import EventBus
from app.queue.memory_diagnostics import (
    get_memory_snapshot,
    log_heartbeat,
    log_message_delta,
    maybe_log_high_watermark,
)
from app.queue.models import PipelineFailureEvent, PipelineSuccessEvent
from app.services.supabase_queue_repository import QueueMessage, SupabaseQueueRepository

if TYPE_CHECKING:
    from app.services.run_lifecycle_adapter import RunLifecycleAdapter
    from app.services.job_definition_service import JobDefinitionService
    from app.services.job_execution import JobExecutionService

# Terminal statuses for idempotency; run already completed
_TERMINAL_STATUSES = frozenset({"succeeded", "failed"})

# Default visibility timeout (seconds) - pipeline can take several minutes
_DEFAULT_VT_SECONDS = 300

# Default poll interval when queue is empty
_DEFAULT_POLL_INTERVAL_SECONDS = 1.0

# SQLSTATE codes that are deterministic and should never be retried
_NON_RETRIABLE_SQLSTATES = frozenset({"23503", "23505"})  # FK violation, unique violation

# Queue read_count ceiling: force terminal if message has been read too many times
_READ_COUNT_CEILING = 20


def _extract_sqlstate(error: BaseException) -> str | None:
    """Extract PostgreSQL SQLSTATE/code from error. Returns None if not found."""
    code = getattr(error, "code", None)
    if code is not None and isinstance(code, str):
        return code.strip()
    if hasattr(error, "args") and error.args:
        first = error.args[0]
        if isinstance(first, dict) and "code" in first:
            c = first["code"]
            return str(c).strip() if c is not None else None
    return None


def _is_non_retriable(error: BaseException) -> bool:
    """True if error is deterministic and should not be retried (e.g. FK violation)."""
    code = _extract_sqlstate(error)
    return code in _NON_RETRIABLE_SQLSTATES if code else False


def _run_pipeline_sync(
    job_execution_service: "JobExecutionService",
    job_definition_service: "JobDefinitionService",
    job_definition_id: str,
    owner_user_id: str,
    run_id: str,
    job_id: str,
    keywords: str,
    definition_snapshot_ref: str | None,
) -> dict:
    """Run snapshot-driven pipeline (call from worker thread)."""
    snapshot_obj = job_definition_service.resolve_for_run(job_definition_id, owner_user_id)
    if not snapshot_obj:
        raise RuntimeError(
            f"Job definition unavailable: job_id={job_definition_id} owner={owner_user_id}"
        )
    trigger_payload = {"raw_input": keywords}
    return job_execution_service.execute_snapshot_run(
        snapshot=snapshot_obj.snapshot,
        run_id=run_id,
        job_id=job_id,
        trigger_payload=trigger_payload,
        definition_snapshot_ref=definition_snapshot_ref or snapshot_obj.snapshot_ref,
        owner_user_id=owner_user_id,
    )


def _normalize_error(error: BaseException) -> str:
    """Produce a normalized error message for UI/history use."""
    msg = str(error).strip() or type(error).__name__
    return msg[:500] if len(msg) > 500 else msg


def _extract_payload(
    msg: QueueMessage,
) -> tuple[str, str, str, str | None, str | None, str | None, str | None, str | None] | None:
    """
    Extract job_id, run_id, keywords, recipient_whatsapp, job_definition_id, job_slug,
    owner_user_id, definition_snapshot_ref from message payload.
    Returns None if payload is malformed.
    """
    p = msg.payload or {}
    job_id = p.get("job_id")
    run_id = p.get("run_id")
    keywords = p.get("keywords")
    if not job_id or not run_id or keywords is None:
        return None
    recipient = p.get("recipient_whatsapp")
    job_def_id = p.get("job_definition_id")
    job_slug = p.get("job_slug")
    owner_user_id = p.get("owner_user_id")
    snapshot_ref = p.get("definition_snapshot_ref")
    return (
        str(job_id),
        str(run_id),
        str(keywords).strip(),
        str(recipient) if recipient else None,
        str(job_def_id) if job_def_id else None,
        str(job_slug) if job_slug else None,
        str(owner_user_id) if owner_user_id else None,
        str(snapshot_ref) if snapshot_ref else None,
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
    run_repo: "RunLifecycleAdapter",
    job_execution_service: "JobExecutionService",
    job_definition_service: "JobDefinitionService",
    event_bus: EventBus,
    *,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
    vt_seconds: int = _DEFAULT_VT_SECONDS,
    retry_delays_seconds: tuple[int, ...] = (5, 30, 60),
    memory_diagnostics_enabled: bool = False,
    memory_tracemalloc_enabled: bool = False,
    memory_limit_mb: float = 512.0,
    memory_heartbeat_interval_seconds: float = 60.0,
) -> None:
    """
    Consume messages from Supabase queue and run the pipeline.
    Persists lifecycle transitions (queued -> running -> succeeded/failed) and events.
    Bounded retries with backoff; final failure marks job/run failed and archives message.
    Runs until cancelled; use asyncio.create_task and cancel on shutdown.
    """
    loop = asyncio.get_event_loop()
    last_heartbeat = time.monotonic()
    crossed_thresholds: set[float] = set()

    while True:
        try:
            messages = queue_repo.read(batch_size=1, vt_seconds=vt_seconds)
        except Exception:
            logger.exception("worker_queue_read_failed")
            await asyncio.sleep(poll_interval_seconds)
            continue

        if not messages:
            # Idle heartbeat
            if memory_diagnostics_enabled:
                now_mono = time.monotonic()
                if now_mono - last_heartbeat >= memory_heartbeat_interval_seconds:
                    last_heartbeat = now_mono
                    snap = get_memory_snapshot()
                    log_heartbeat(
                        rss_mb=snap["rss_mb"],
                        gc_counts=snap["gc_counts"],
                        gc_objects=snap["gc_objects"],
                        num_threads=snap["num_threads"],
                        open_fds=snap["open_fds"],
                        fd_socket=snap.get("fd_socket", 0),
                        fd_pipe=snap.get("fd_pipe", 0),
                        fd_anon=snap.get("fd_anon", 0),
                        fd_file=snap.get("fd_file", 0),
                        traced_current_mb=snap["traced_current_mb"],
                        traced_peak_mb=snap["traced_peak_mb"],
                        active_msg_id=None,
                        active_run_id=None,
                    )
                    crossed_thresholds = maybe_log_high_watermark(
                        snap["rss_mb"],
                        memory_limit_mb,
                        crossed_thresholds,
                        None,
                        None,
                        include_tracemalloc_snapshot=memory_tracemalloc_enabled,
                        fd_socket=snap.get("fd_socket", 0),
                        fd_pipe=snap.get("fd_pipe", 0),
                        fd_anon=snap.get("fd_anon", 0),
                        fd_file=snap.get("fd_file", 0),
                    )
            await asyncio.sleep(poll_interval_seconds)
            continue

        for msg in messages:
            # Heartbeat before processing
            if memory_diagnostics_enabled:
                now_mono = time.monotonic()
                if now_mono - last_heartbeat >= memory_heartbeat_interval_seconds:
                    last_heartbeat = now_mono
                    snap = get_memory_snapshot()
                    log_heartbeat(
                        rss_mb=snap["rss_mb"],
                        gc_counts=snap["gc_counts"],
                        gc_objects=snap["gc_objects"],
                        num_threads=snap["num_threads"],
                        open_fds=snap["open_fds"],
                        fd_socket=snap.get("fd_socket", 0),
                        fd_pipe=snap.get("fd_pipe", 0),
                        fd_anon=snap.get("fd_anon", 0),
                        fd_file=snap.get("fd_file", 0),
                        traced_current_mb=snap["traced_current_mb"],
                        traced_peak_mb=snap["traced_peak_mb"],
                        active_msg_id=msg.message_id,
                        active_run_id=(
                            (msg.payload or {}).get("run_id")
                            if msg.payload else None
                        ),
                    )
                    crossed_thresholds = maybe_log_high_watermark(
                        snap["rss_mb"],
                        memory_limit_mb,
                        crossed_thresholds,
                        msg.message_id,
                        (msg.payload or {}).get("run_id") if msg.payload else None,
                        include_tracemalloc_snapshot=memory_tracemalloc_enabled,
                        fd_socket=snap.get("fd_socket", 0),
                        fd_pipe=snap.get("fd_pipe", 0),
                        fd_anon=snap.get("fd_anon", 0),
                        fd_file=snap.get("fd_file", 0),
                    )
            try:
                await _process_message(
                    msg,
                    queue_repo,
                    run_repo,
                    job_execution_service,
                    job_definition_service,
                    event_bus,
                    loop,
                    retry_delays_seconds=retry_delays_seconds,
                    memory_diagnostics_enabled=memory_diagnostics_enabled,
                    memory_tracemalloc_enabled=memory_tracemalloc_enabled,
                    memory_limit_mb=memory_limit_mb,
                    memory_crossed_thresholds_ref=crossed_thresholds,
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
    run_repo: "RunLifecycleAdapter",
    event_bus: EventBus,
    error: BaseException,
) -> None:
    """Best-effort: persist failed, emit event, archive. Called when _process_message raises."""
    extracted = _extract_payload(msg)
    if extracted is None:
        queue_repo.archive(msg.message_id)
        return
    job_id, run_id, keywords, recipient_whatsapp, _jd, _js, _owner, _snap = extracted
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
    run_repo: "RunLifecycleAdapter",
    job_execution_service: "JobExecutionService",
    job_definition_service: "JobDefinitionService",
    event_bus: EventBus,
    loop: asyncio.AbstractEventLoop,
    *,
    retry_delays_seconds: tuple[int, ...] = (5, 30, 60),
    memory_diagnostics_enabled: bool = False,
    memory_tracemalloc_enabled: bool = False,
    memory_limit_mb: float = 512.0,
    memory_crossed_thresholds_ref: set[float] | None = None,
) -> None:
    """Process a single queue message: validate, idempotency check, bounded retries, execute, persist, archive."""
    mem_before_mb = get_memory_snapshot()["rss_mb"] if memory_diagnostics_enabled else 0.0

    def _log_delta(result: str, attempt: int, error_code: str | None = None) -> None:
        if memory_diagnostics_enabled and extracted is not None:
            snap = get_memory_snapshot()
            mem_after_mb = snap["rss_mb"]
            log_message_delta(
                mem_before_mb=mem_before_mb,
                mem_after_mb=mem_after_mb,
                msg_id=msg.message_id,
                run_id=extracted[1],
                job_id=extracted[0],
                attempt=attempt,
                result=result,
                error_code=error_code,
            )
            if memory_crossed_thresholds_ref is not None:
                crossed = maybe_log_high_watermark(
                    mem_after_mb,
                    memory_limit_mb,
                    memory_crossed_thresholds_ref,
                    msg.message_id,
                    extracted[1],
                    include_tracemalloc_snapshot=memory_tracemalloc_enabled,
                    fd_socket=snap.get("fd_socket", 0),
                    fd_pipe=snap.get("fd_pipe", 0),
                    fd_anon=snap.get("fd_anon", 0),
                    fd_file=snap.get("fd_file", 0),
                )
                memory_crossed_thresholds_ref.clear()
                memory_crossed_thresholds_ref.update(crossed)

    extracted = _extract_payload(msg)
    if extracted is None:
        logger.warning(
            "worker_malformed_payload | msg_id={} payload_keys={}",
            msg.message_id,
            list((msg.payload or {}).keys()),
        )
        queue_repo.archive(msg.message_id)
        return

    (
        job_id,
        run_id,
        keywords,
        recipient_whatsapp,
        job_definition_id,
        job_slug,
        owner_user_id,
        definition_snapshot_ref,
    ) = extracted

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
        _log_delta("duplicate_skip", 0)
        queue_repo.archive(msg.message_id)
        return

    # Bounded retry loop
    retry_count = run_repo.get_job_retry_count(job_id)
    max_retries = len(retry_delays_seconds)

    # Defense-in-depth: force terminal if queue read_count exceeds ceiling
    if msg.read_count >= _READ_COUNT_CEILING:
        logger.warning(
            "worker_read_count_ceiling | msg_id={} run_id={} read_count={} ceiling={}",
            msg.message_id,
            run_id,
            msg.read_count,
            _READ_COUNT_CEILING,
        )
        _log_delta("failed_terminal", retry_count, "read_count_ceiling")
        _mark_failed_and_archive(
            msg,
            queue_repo,
            run_repo,
            event_bus,
            job_id,
            run_id,
            keywords,
            recipient_whatsapp,
            "read_count exceeded ceiling; forcing terminal",
            datetime.now(timezone.utc),
            RuntimeError("read_count exceeded ceiling"),
        )
        return

    while True:
        now = datetime.now(timezone.utc)
        try:
            # Persist running
            run_repo.update_job_status(
                job_id, "running", started_at=now, retry_count=retry_count
            )
            run_repo.update_run(run_id, status="running")
            event_payload: dict = {"keywords_preview": keywords[:80]}
            if job_definition_id:
                event_payload["job_definition_id"] = job_definition_id
            if job_slug:
                event_payload["job_slug"] = job_slug
            run_repo.insert_event(run_id, "pipeline_started", event_payload)
        except Exception as e:
            logger.exception(
                "worker_persist_running_failed | job_id={} run_id={}",
                job_id,
                run_id,
            )
            err_msg = _normalize_error(e)
            if _is_non_retriable(e):
                logger.info(
                    "worker_non_retriable_terminal | job_id={} run_id={} sqlstate={}",
                    job_id,
                    run_id,
                    _extract_sqlstate(e),
                )
                _log_delta("failed_terminal", retry_count + 1, _extract_sqlstate(e))
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
            _log_delta("failed_terminal", retry_count + 1)
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

        # Execute pipeline (snapshot-driven)
        if not owner_user_id or not job_definition_id:
            raise ValueError(
                "owner_user_id and job_definition_id required for snapshot execution"
            )
        try:
            result = await loop.run_in_executor(
                None,
                lambda: _run_pipeline_sync(
                    job_execution_service,
                    job_definition_service,
                    job_definition_id,
                    owner_user_id,
                    run_id,
                    job_id,
                    keywords,
                    definition_snapshot_ref,
                ),
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
            if _is_non_retriable(e):
                logger.info(
                    "worker_non_retriable_terminal | job_id={} run_id={} sqlstate={}",
                    job_id,
                    run_id,
                    _extract_sqlstate(e),
                )
                _log_delta("failed_terminal", retry_count + 1, _extract_sqlstate(e))
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
            _log_delta("failed_terminal", retry_count + 1)
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
        except Exception as e:
            logger.exception(
                "worker_persist_success_failed | job_id={} run_id={}",
                job_id,
                run_id,
            )
            err_msg = _normalize_error(e)
            if _is_non_retriable(e):
                logger.info(
                    "worker_non_retriable_terminal | job_id={} run_id={} sqlstate={}",
                    job_id,
                    run_id,
                    _extract_sqlstate(e),
                )
                _log_delta("failed_terminal", retry_count + 1, _extract_sqlstate(e))
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
            _log_delta("failed_terminal", retry_count + 1)
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

        _log_delta("success", retry_count + 1)
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
    run_repo: "RunLifecycleAdapter",
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
    run_repo: "RunLifecycleAdapter",
    event_bus: EventBus,
    job_id: str,
    run_id: str,
    keywords: str,
    recipient_whatsapp: str | None,
    err_msg: str,
    now: datetime,
    error: BaseException,
) -> None:
    """Best-effort persist failed status, emit event, and archive."""
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
        logger.exception("worker_failure_event_publish_failed | job_id={}", job_id)
    try:
        queue_repo.archive(msg.message_id)
    except Exception:
        logger.exception("worker_failure_archive_failed | msg_id={}", msg.message_id)
        raise
