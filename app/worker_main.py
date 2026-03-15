"""Dedicated worker process entrypoint for Supabase queue consumer."""

import asyncio
import os
import signal
import sys
from pathlib import Path

from loguru import logger

from app.env_bootstrap import bootstrap_env, log_env_masked
from app.integrations.supabase_config import load_supabase_config
from app.integrations.supabase_client import create_supabase_client
from app.queue.events import EventBus, subscribe_to_success
from app.queue.memory_diagnostics import (
    parse_diagnostics_enabled,
    parse_heartbeat_interval_seconds,
    parse_memory_limit_mb,
    parse_tracemalloc_enabled,
    start_tracemalloc_if_enabled,
)
from app.queue.worker import _parse_retry_delays, run_worker_loop
from app.repositories import (
    YamlAppConfigRepository,
    YamlConnectorInstanceRepository,
    YamlJobRepository,
    YamlStepTemplateRepository,
    YamlTargetSchemaRepository,
    YamlTargetTemplateRepository,
    YamlTargetRepository,
    YamlTriggerRepository,
)
from app.services.claude_service import ClaudeService
from app.services.communicator import Communicator
from app.services.freepik_service import FreepikService
from app.services.google_places_service import GooglePlacesService
from app.services.job_definition_service import JobDefinitionService
from app.services.job_execution import JobExecutionService
from app.repositories import YamlRunRepository
from app.services.notion_service import NotionService
from app.services.run_lifecycle_adapter import RunLifecycleAdapter
from app.services.supabase_queue_repository import SupabaseQueueRepository
from app.services.target_service import TargetService
from app.services.trigger_service import TriggerService
from app.services.validation_service import ValidationService
from app.services.whatsapp_service import WhatsAppService

# Worker tuning (optional env overrides; parsed after bootstrap_env in main)
_WORKER_POLL_INTERVAL = float(os.environ.get("WORKER_POLL_INTERVAL_SECONDS", "1.0"))
_WORKER_VT_SECONDS = int(os.environ.get("WORKER_VT_SECONDS", "300"))

# Reuse main's log format for consistency
_CONTEXT_KEYS = (
    "run_id", "global_pipeline", "stage", "keywords_preview", "error",
    "rss_mb", "gc_counts", "gc_objects", "num_threads", "open_fds",
    "fd_socket", "fd_pipe", "fd_anon", "fd_file",
    "traced_current_mb", "traced_peak_mb",
    "mem_before_mb", "mem_after_mb", "mem_delta_mb",
    "msg_id", "job_id", "attempt", "result", "error_code",
)


def _escape_braces(value: object) -> str:
    return str(value).replace("{", "{{").replace("}", "}}")


def _log_format(record: dict) -> str:
    parts = [
        record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "|",
        record["level"].name,
        "|",
        f"{record['name']}:{record['function']}:{record['line']}",
        "-",
        _escape_braces(record["message"]),
    ]
    extra = record.get("extra", {})
    ctx_parts = [
        f"{k}={_escape_braces(extra[k])}"
        for k in _CONTEXT_KEYS
        if k in extra and extra[k] is not None and extra[k] != ""
    ]
    if ctx_parts:
        parts.append("|")
        parts.append(" ".join(ctx_parts))
    exc = record.get("exception")
    if exc is not None:
        exc_type = getattr(exc, "type", None)
        exc_type_name = exc_type.__name__ if exc_type is not None else "Exception"
        exc_value = getattr(exc, "value", "")
        parts.append("|")
        parts.append(
            f"exception={_escape_braces(exc_type_name)}:{_escape_braces(exc_value)}"
        )
    return " ".join(parts) + "\n"


def _configure_logger() -> None:
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logger.remove()
    logger.add(sys.stderr, format=_log_format, level=log_level)
    log_path = os.environ.get("LOG_FILE_PATH", "logs/app.log")
    log_rotation = os.environ.get("LOG_FILE_ROTATION", "10 MB")
    log_retention = os.environ.get("LOG_FILE_RETENTION", "3")
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_path,
        format=_log_format,
        rotation=log_rotation,
        retention=int(log_retention),
        level=log_level,
    )
    logger.info(
        "worker_logger_configured | level={} file={}",
        log_level,
        log_path,
    )


def _cleanup_queue_repo(queue_repo: object) -> None:
    """Best-effort close of queue repository session. Logs errors, does not raise."""
    close_fn = getattr(queue_repo, "close", None)
    if callable(close_fn):
        try:
            close_fn()
        except Exception:
            logger.exception("worker_queue_repo_close_failed")


def main() -> None:
    """Bootstrap services and run worker loop until shutdown."""
    bootstrap_env()
    _configure_logger()
    log_env_masked()

    notion_key = os.environ.get("NOTION_API_KEY")
    if not notion_key:
        raise RuntimeError("NOTION_API_KEY environment variable is required")
    anthropic_token = os.environ.get("ANTHROPIC_TOKEN")
    if not anthropic_token:
        raise RuntimeError("ANTHROPIC_TOKEN environment variable is required")
    google_places_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not google_places_key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY environment variable is required")

    supabase_config = load_supabase_config()
    supabase_client = create_supabase_client(supabase_config)
    queue_repo = SupabaseQueueRepository(supabase_client, supabase_config)
    yaml_run_repo = YamlRunRepository()
    run_repo = RunLifecycleAdapter(yaml_run_repo)

    dry_run = os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes")
    notion_svc = NotionService(api_key=notion_key, dry_run=dry_run)
    notion_svc.initialize()

    claude_svc = ClaudeService(api_key=anthropic_token)
    google_places_svc = GooglePlacesService(api_key=google_places_key)
    freepik_key = os.environ.get("FREEPIK_API_KEY")
    freepik_svc = FreepikService(api_key=freepik_key) if freepik_key else None

    step_template_repo = YamlStepTemplateRepository()
    target_template_repo = YamlTargetTemplateRepository()
    trigger_repo = YamlTriggerRepository()
    target_repo = YamlTargetRepository()
    target_schema_repo = YamlTargetSchemaRepository()
    app_config_repo = YamlAppConfigRepository()
    connector_instance_repo = YamlConnectorInstanceRepository()
    validation_service = ValidationService(
        trigger_repo=trigger_repo,
        target_repo=target_repo,
        target_schema_repo=target_schema_repo,
        step_template_repo=step_template_repo,
        app_config_repo=app_config_repo,
        connector_instance_repo=connector_instance_repo,
        target_template_repo=target_template_repo,
    )
    job_repo = YamlJobRepository(validation_service=validation_service)
    trigger_service = TriggerService(trigger_repository=trigger_repo)
    target_service = TargetService(
        target_repository=target_repo,
        target_schema_repository=target_schema_repo,
    )
    job_definition_service = JobDefinitionService(
        job_repository=job_repo,
        trigger_service=trigger_service,
        target_service=target_service,
    )
    job_execution_service = JobExecutionService(
        notion_service=notion_svc,
        claude_service=claude_svc,
        google_places_service=google_places_svc,
        freepik_service=freepik_svc,
        dry_run=dry_run,
        run_repository=yaml_run_repo,
    )

    event_bus = EventBus()
    subscribe_to_success(event_bus)

    twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    twilio_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    twilio_from = os.environ.get("TWILIO_WHATSAPP_NUMBER", "").strip()
    if twilio_sid and twilio_token and twilio_from:
        whatsapp_svc = WhatsAppService(
            account_sid=twilio_sid,
            auth_token=twilio_token,
            from_number=twilio_from,
        )
        status_enabled = os.environ.get("WHATSAPP_STATUS_ENABLED", "1").strip().lower() in (
            "1", "true", "yes",
        )
        default_recipient = os.environ.get("WHATSAPP_STATUS_RECIPIENT_DEFAULT", "").strip() or None
        max_error_chars = int(os.environ.get("WHATSAPP_STATUS_MAX_ERROR_CHARS", "300"))
        communicator = Communicator(
            whatsapp_service=whatsapp_svc,
            enabled=status_enabled,
            default_recipient=default_recipient,
            max_error_chars=max_error_chars,
        )
        event_bus.subscribe_success(communicator.notify_pipeline_success)
        event_bus.subscribe_failure(communicator.notify_pipeline_failure)
    else:
        logger.info(
            "worker_whatsapp_skipped | twilio credentials not configured"
        )

    retry_delays = _parse_retry_delays(
        os.environ.get("WORKER_RETRY_DELAYS_SECONDS", "")
    )
    memory_diagnostics_enabled = parse_diagnostics_enabled(
        os.environ.get("WORKER_MEMORY_DIAGNOSTICS_ENABLED", "")
    )
    memory_tracemalloc_enabled = parse_tracemalloc_enabled(
        os.environ.get("WORKER_MEMORY_TRACEMALLOC_ENABLED", "")
    )
    memory_limit_mb = parse_memory_limit_mb(
        os.environ.get("WORKER_MEMORY_LIMIT_MB", "")
    )
    memory_heartbeat_interval = parse_heartbeat_interval_seconds(
        os.environ.get("WORKER_MEMORY_HEARTBEAT_INTERVAL_SECONDS", "")
    )
    start_tracemalloc_if_enabled(memory_tracemalloc_enabled)

    logger.info(
        "worker_starting | poll_interval={} vt_seconds={} retry_delays={} "
        "memory_diagnostics={} memory_tracemalloc={}",
        _WORKER_POLL_INTERVAL,
        _WORKER_VT_SECONDS,
        retry_delays,
        memory_diagnostics_enabled,
        memory_tracemalloc_enabled,
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    worker_task = loop.create_task(
        run_worker_loop(
            queue_repo,
            run_repo,
            job_execution_service,
            job_definition_service,
            event_bus,
            poll_interval_seconds=_WORKER_POLL_INTERVAL,
            vt_seconds=_WORKER_VT_SECONDS,
            retry_delays_seconds=retry_delays,
            memory_diagnostics_enabled=memory_diagnostics_enabled,
            memory_tracemalloc_enabled=memory_tracemalloc_enabled,
            memory_limit_mb=memory_limit_mb,
            memory_heartbeat_interval_seconds=memory_heartbeat_interval,
        )
    )

    def shutdown() -> None:
        logger.info("worker_shutdown_requested")
        worker_task.cancel()

    try:
        loop.add_signal_handler(signal.SIGTERM, shutdown)
        loop.add_signal_handler(signal.SIGINT, shutdown)
    except NotImplementedError:
        pass  # Windows does not support add_signal_handler

    try:
        loop.run_until_complete(worker_task)
    except asyncio.CancelledError:
        logger.info("worker_stopped")
    finally:
        _cleanup_queue_repo(queue_repo)
        loop.close()


if __name__ == "__main__":
    main()
