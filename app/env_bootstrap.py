"""Environment bootstrap: load .env files at startup with safe precedence."""

import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# Static env key list used for startup env logging.
# Keep this list in sync with envs/env.template.
ENV_TEMPLATE_KEYS: tuple[str, ...] = (
    "BASE_URL",
    "SECRET",
    "CORS_ALLOWED_ORIGINS",
    "SUPABASE_PROJECT_REF",
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_QUEUE_NAME",
    "SUPABASE_TABLE_PLATFORM_JOBS",
    "SUPABASE_TABLE_PIPELINE_RUNS",
    "SUPABASE_TABLE_PIPELINE_RUN_EVENTS",
    "NOTION_API_KEY",
    "ANTHROPIC_TOKEN",
    "GOOGLE_PLACES_API_KEY",
    "FREEPIK_API_KEY",
    "DRY_RUN",
    "LOCATIONS_ASYNC_ENABLED",
    "GOOGLE_PLACE_DETAILS_FETCH",
    "LOCATIONS_CACHE_TTL_SECONDS",
    "LOCATION_MATCH_MIN_CONFIDENCE",
    "LOCATION_RELATION_REQUIRED",
    "LOG_LEVEL",
    "LOG_FILE_PATH",
    "LOG_FILE_ROTATION",
    "LOG_FILE_RETENTION",
    "WORKER_RETRY_DELAYS_SECONDS",
    "WORKER_MEMORY_DIAGNOSTICS_ENABLED",
    "WORKER_MEMORY_LIMIT_MB",
    "WORKER_MEMORY_HEARTBEAT_INTERVAL_SECONDS",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_WHATSAPP_NUMBER",
    "WHATSAPP_STATUS_RECIPIENT_DEFAULT",
    "WHATSAPP_STATUS_ENABLED",
    "WHATSAPP_STATUS_MAX_ERROR_CHARS",
)

# Keys whose values are masked in logs. Must be a subset of keys parsed from env.template.
SENSITIVE_ENV_KEYS: frozenset[str] = frozenset({
    "SECRET",
    "SUPABASE_SECRET_KEY",
    "NOTION_API_KEY",
    "ANTHROPIC_TOKEN",
    "GOOGLE_PLACES_API_KEY",
    "FREEPIK_API_KEY",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
})

# Env file search order: repo root .env, Render secret file, local convention
DEFAULT_ENV_PATHS = (
    Path(__file__).resolve().parent.parent / ".env",
    Path("/etc/secrets/.env"),
    Path(__file__).resolve().parent.parent / "envs" / "local.env",
)


def load_env_file(paths: tuple[Path, ...] | None = None) -> Path | None:
    """Load first existing .env file; process env vars override file values."""
    search_paths = paths if paths is not None else DEFAULT_ENV_PATHS
    logger.info(
        "env_bootstrap | searching paths | {}",
        ", ".join(str(p) for p in search_paths),
    )
    for path in search_paths:
        if path.is_file():
            load_dotenv(path, override=False)
            logger.info("env_bootstrap | loaded env file | {}", path)
            return path
    logger.warning("env_bootstrap | no env file found")
    return None


def bootstrap_env(paths: tuple[Path, ...] | None = None) -> None:
    """Load env file at startup; process env vars override file values."""
    load_env_file(paths)


def log_env_masked() -> None:
    """
    Log env variables declared in ENV_TEMPLATE_KEYS. Sensitive keys (SENSITIVE_ENV_KEYS)
    are masked with length-preserving asterisks; others are logged as-is.
    Unset keys are logged as [unset].
    """
    for key in ENV_TEMPLATE_KEYS:
        value = os.environ.get(key)
        if value is None or value == "":
            logger.info("env | {}={}", key, "[unset]")
        elif key in SENSITIVE_ENV_KEYS:
            logger.info("env | {}={}", key, "*" * len(value))
        else:
            logger.info("env | {}={}", key, value)
