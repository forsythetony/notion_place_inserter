"""FastAPI application with secret-based authorization."""

import hmac
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.services.claude_service import ClaudeService
from app.services.freepik_service import FreepikService
from app.services.google_places_service import GooglePlacesService
from app.services.location_service import LocationService
from app.services.notion_service import NotionService
from app.services.places_service import PlacesService
from app.env_bootstrap import bootstrap_env, log_env_masked
from app.integrations.supabase_config import load_supabase_config
from app.integrations.supabase_client import create_supabase_client
from app.repositories import (
    PostgresAppConfigRepository,
    PostgresConnectorInstanceRepository,
    PostgresJobRepository,
    PostgresRunRepository,
    PostgresStepTemplateRepository,
    PostgresTargetRepository,
    PostgresTargetSchemaRepository,
    PostgresTargetTemplateRepository,
    PostgresTriggerJobLinkRepository,
    PostgresTriggerRepository,
)
from app.repositories.id_mapping import verify_mapping_consistency
from app.services.bootstrap_provisioning import BootstrapProvisioningService
from app.services.postgres_seed_service import PostgresBootstrapProvisioningService
from app.services.validation_service import ValidationService
from app.services.trigger_service import TriggerService
from app.services.target_service import TargetService
from app.services.schema_sync_service import SchemaSyncService
from app.services.job_definition_service import JobDefinitionService
from app.services.job_execution import JobExecutionService
from app.services.supabase_auth_repository import SupabaseAuthRepository
from app.services.supabase_queue_repository import SupabaseQueueRepository
from app.routes import auth_context, invitations, locations, management, signup, test
from app.services.signup_orchestration_service import SignupOrchestrationService

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
    log_env_masked()

    notion_key = os.environ.get("NOTION_API_KEY")
    if not notion_key:
        logger.error("startup_failed | reason=missing_env var=NOTION_API_KEY")
        raise RuntimeError("NOTION_API_KEY environment variable is required")
    anthropic_token = os.environ.get("ANTHROPIC_TOKEN")
    if not anthropic_token:
        logger.error("startup_failed | reason=missing_env var=ANTHROPIC_TOKEN")
        raise RuntimeError("ANTHROPIC_TOKEN environment variable is required")
    google_places_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not google_places_key:
        logger.error("startup_failed | reason=missing_env var=GOOGLE_PLACES_API_KEY")
        raise RuntimeError("GOOGLE_PLACES_API_KEY environment variable is required")

    supabase_config = load_supabase_config()
    supabase_client = create_supabase_client(supabase_config)
    app.state.supabase_client = supabase_client
    app.state.supabase_queue_repository = SupabaseQueueRepository(
        supabase_client, supabase_config
    )
    postgres_run_repo = PostgresRunRepository(supabase_client)
    app.state.supabase_run_repository = postgres_run_repo
    app.state.trigger_job_link_repository = PostgresTriggerJobLinkRepository(supabase_client)

    enable_bootstrap = os.environ.get("ENABLE_BOOTSTRAP_PROVISIONING", "1").strip().lower() in (
        "1", "true", "yes",
    )
    if enable_bootstrap:
        try:
            verify_mapping_consistency(supabase_client)
            bootstrap_svc: BootstrapProvisioningService = PostgresBootstrapProvisioningService(
                supabase_client, link_repo=app.state.trigger_job_link_repository
            )
            bootstrap_svc.seed_catalog_if_needed()
            app.state.bootstrap_provisioning_service = bootstrap_svc
        except Exception as e:
            logger.exception("startup_bootstrap_seed_failed | error={}", e)
            raise
    else:
        app.state.bootstrap_provisioning_service = None
    app.state.supabase_auth_repository = SupabaseAuthRepository(
        supabase_client, supabase_config
    )
    app.state.signup_orchestration_service = SignupOrchestrationService(
        supabase_client, app.state.supabase_auth_repository
    )

    dry_run = os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes")
    notion_svc = NotionService(api_key=notion_key, dry_run=dry_run)
    notion_svc.initialize()

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

    # Wire validation into save paths (p3_pr04); Phase 4 uses Postgres repos
    step_template_repo = PostgresStepTemplateRepository(supabase_client)
    target_template_repo = PostgresTargetTemplateRepository(supabase_client)
    trigger_repo = PostgresTriggerRepository(supabase_client)
    target_repo = PostgresTargetRepository(supabase_client)
    target_schema_repo = PostgresTargetSchemaRepository(supabase_client)
    app_config_repo = PostgresAppConfigRepository(supabase_client)
    connector_instance_repo = PostgresConnectorInstanceRepository(supabase_client)
    validation_service = ValidationService(
        trigger_repo=trigger_repo,
        target_repo=target_repo,
        target_schema_repo=target_schema_repo,
        step_template_repo=step_template_repo,
        app_config_repo=app_config_repo,
        connector_instance_repo=connector_instance_repo,
        target_template_repo=target_template_repo,
    )
    job_repo = PostgresJobRepository(supabase_client, validation_service=validation_service)
    trigger_repo.set_validation_service(validation_service)
    target_repo.set_validation_service(validation_service)
    app.state.job_repository = job_repo
    app.state.trigger_repository = trigger_repo
    app.state.target_repository = target_repo
    app.state.target_schema_repository = target_schema_repo
    app.state.app_config_repository = app_config_repo
    app.state.connector_instance_repository = connector_instance_repo

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
    schema_sync_service = SchemaSyncService(
        target_repository=target_repo,
        target_schema_repository=target_schema_repo,
        connector_instance_repository=connector_instance_repo,
        notion_service=notion_svc,
    )
    app.state.trigger_service = trigger_service
    app.state.target_service = target_service
    app.state.job_definition_service = job_definition_service
    app.state.schema_sync_service = schema_sync_service

    job_execution_service = JobExecutionService(
        notion_service=notion_svc,
        claude_service=app.state.claude_service,
        google_places_service=app.state.google_places_service,
        freepik_service=freepik_svc,
        dry_run=dry_run,
        run_repository=postgres_run_repo,
    )
    app.state.job_execution_service = job_execution_service

    async_enabled = os.environ.get("LOCATIONS_ASYNC_ENABLED", "1").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    app.state.locations_async_enabled = async_enabled

    yield


app = FastAPI(title="Hello World API", lifespan=lifespan)

SECRET = os.environ.get("SECRET", "")

# CORS: allow frontend origins from env (comma-separated)
_cors_origins_raw = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

app.include_router(auth_context.router)
app.include_router(management.router)
app.include_router(signup.router)
app.include_router(invitations.router)
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
