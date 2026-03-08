"""FastAPI application with secret-based authorization."""

import hmac
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from loguru import logger

from app.routes import locations, test
from app.services.claude_service import ClaudeService
from app.services.freepik_service import FreepikService
from app.services.google_places_service import GooglePlacesService
from app.services.location_service import LocationService
from app.services.notion_service import NotionService
from app.services.places_service import PlacesService

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
)


def _log_format(record: dict) -> str:
    """Format log record with optional orchestration context."""
    parts = [
        record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "|",
        record["level"].name,
        "|",
        f"{record['name']}:{record['function']}:{record['line']}",
        "-",
        record["message"],
    ]
    extra = record.get("extra", {})
    ctx_parts = [
        f"{k}={extra[k]}"
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
    logger.remove()
    logger.add(sys.stderr, format=_log_format)

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
    )


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

    yield
    # shutdown (no cleanup needed)


app = FastAPI(title="Hello World API", lifespan=lifespan)

SECRET = os.environ.get("secret", "")

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
