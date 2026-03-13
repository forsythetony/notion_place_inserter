"""FastAPI application with secret-based authorization."""

import asyncio
import hmac
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from loguru import logger

from app.queue import (
    create_location_queue,
    subscribe_to_success,
    run_worker_loop,
    EventBus,
)
from app.routes import locations, test
from app.services.claude_service import ClaudeService
from app.services.communicator import Communicator
from app.services.freepik_service import FreepikService
from app.services.google_places_service import GooglePlacesService
from app.services.location_service import LocationService
from app.services.notion_service import NotionService
from app.services.places_service import PlacesService
from app.services.whatsapp_service import WhatsAppService

from app.env_bootstrap import bootstrap_env
from app.integrations.supabase_config import load_supabase_config
from app.integrations.supabase_client import create_supabase_client
from app.services.supabase_queue_repository import SupabaseQueueRepository
from app.services.supabase_run_repository import SupabaseRunRepository

# Bootstrap env at import so all runtime lookups see file values (unless overridden)
bootstrap_env()

# Context keys to render when present (pipeline orchestration metadata)
_CONTEXT_KEYS = (
    "run_id",
    "global_pipeline",
    "global_pipeline_name",
    "stage",
    "stage_name",
    "pipeline",
    "pipeline_name",
    "step",
    "step_name",
    "property_name",
    "event",
    "duration_ms",
    "property_count",
    "keywords_preview",
    "dry_run",
    "failed_pipeline_count",
    "error",
    "candidate_context",
    "claude_raw_value",
    "canonical_values",
    "claude_selected_value",
    "claude_selected_values",
    "is_new_neighborhood",
    "parsed_value",
    "parsed_confidence",
    "parsed_source",
    "direct_selected_value",
    "deterministic_signal_type",
    "deterministic_selected_value",
    "google_neighborhood_signals",
    "place_id",
    "address_component_count",
    "neighborhood_options",
    "address_components_neighborhood_subset",
    "claude_prompt_preview",
    "suggested_value",
    "selected_option",
)


def _escape_braces(value: object) -> str:
    """Escape braces so dynamic loguru format strings stay valid."""
    return str(value).replace("{", "{{").replace("}", "}}")


def _log_format(record: dict) -> str:
    """Format log record with optional orchestration context."""
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
    return " ".join(parts) + "\n"


def _configure_logger() -> None:
    """Configure loguru to render orchestration context in output.

    Adds two sinks: stderr (console) and an auto-rotated file. Rotated files
    are deleted (retention) rather than compressed, for resource-constrained
    environments.
    """
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
    logger.info("logger_configured | level={} file={}", log_level, log_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    _configure_logger()

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
    app.state.supabase_client = supabase_client
    app.state.supabase_queue_repository = SupabaseQueueRepository(
        supabase_client, supabase_config
    )
    app.state.supabase_run_repository = SupabaseRunRepository(
        supabase_client, supabase_config
    )

    notion_svc = NotionService(api_key=notion_key)
    notion_svc.initialize()

    dry_run = os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes")

    freepik_key = os.environ.get("FREEPIK_API_KEY")
    freepik_svc = FreepikService(api_key=freepik_key) if freepik_key else None

    app.state.notion_service = notion_svc
    app.state.claude_service = ClaudeService(api_key=anthropic_token)
    app.state.google_places_service = GooglePlacesService(api_key=google_places_key)
    app.state.freepik_service = freepik_svc
    app.state.location_service = LocationService(
        notion_service=notion_svc,
        claude_service=app.state.claude_service,
    )
    app.state.places_service = PlacesService(
        notion_svc,
        claude_service=app.state.claude_service,
        google_places_service=app.state.google_places_service,
        location_service=app.state.location_service,
        freepik_service=freepik_svc,
        dry_run=dry_run,
    )

    async_enabled = os.environ.get("LOCATIONS_ASYNC_ENABLED", "1").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    app.state.locations_async_enabled = async_enabled

    if async_enabled:
        job_queue = create_location_queue()
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
                "1",
                "true",
                "yes",
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
                "whatsapp_status_skipped | twilio credentials not configured; run-status notifications disabled"
            )

        app.state.location_job_queue = job_queue
        app.state.location_event_bus = event_bus
        worker_task = asyncio.create_task(
            run_worker_loop(job_queue, app.state.places_service, event_bus)
        )
        app.state.location_worker_task = worker_task
    else:
        app.state.location_job_queue = None
        app.state.location_event_bus = None
        app.state.location_worker_task = None

    yield

    if async_enabled and app.state.location_worker_task:
        app.state.location_worker_task.cancel()
        try:
            await app.state.location_worker_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Hello World API", lifespan=lifespan)

SECRET = os.environ.get("SECRET", "")

app.include_router(locations.router)
app.include_router(test.router)


@app.get("/")
def hello(authorization: str | None = Header(default=None)):
    """Return a greeting if the Authorization header matches the secret."""
    if not SECRET:
        logger.error("SECRET environment variable is not set")
        raise HTTPException(status_code=500, detail="Server misconfiguration")

    if not authorization or not hmac.compare_digest(authorization, SECRET):
        logger.warning("Unauthorized request: missing or invalid Authorization header")
        raise HTTPException(status_code=401, detail="Unauthorized")

    return {"message": "Hello there!"}
