"""Typed Supabase environment configuration with validation."""

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SupabaseConfig:
    """Backend Supabase configuration (URL, secret key, queue/table names)."""

    url: str
    secret_key: str
    queue_name: str
    table_platform_jobs: str
    table_pipeline_runs: str
    table_pipeline_run_events: str
    table_user_profiles: str
    table_invitation_codes: str


def _require_non_empty(value: str, env_var: str) -> str:
    """Return stripped value or raise with actionable error."""
    if not value or not value.strip():
        raise RuntimeError(
            f"{env_var} environment variable is required for backend Supabase integration. "
            f"Set it in envs/local.env or your deployment environment."
        )
    return value.strip()


def _require_valid_supabase_url(value: str, env_var: str) -> str:
    """
    Validate URL is non-empty and either:
    - https:// (production/hosted Supabase), or
    - http:// for localhost/127.0.0.1 (local Supabase).
    Rejects http:// for non-local hosts (insecure).
    """
    v = _require_non_empty(value, env_var)
    if re.match(r"^https://[^\s]+$", v):
        return v
    # Allow http only for local Supabase
    if re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?[^\s]*$", v, re.IGNORECASE):
        return v
    raise RuntimeError(
        f"{env_var} must be a valid https URL (e.g. https://<project-ref>.supabase.co), "
        f"or http://127.0.0.1:54321 for local Supabase. Got: {v[:50]}{'...' if len(v) > 50 else ''}"
    )


def _default_queue_name() -> str:
    """Default queue name from env or constant."""
    v = os.environ.get("SUPABASE_QUEUE_NAME", "").strip()
    return v if v else "locations_jobs"


def _default_table(name: str, default: str) -> str:
    """Default table name from env or constant."""
    env_key = f"SUPABASE_TABLE_{name.upper()}"
    v = os.environ.get(env_key, "").strip()
    return v if v else default


def load_supabase_config() -> SupabaseConfig:
    """
    Load and validate Supabase backend config from environment.
    Raises RuntimeError with clear message when required vars are missing or malformed.
    """
    url = _require_valid_supabase_url(
        os.environ.get("SUPABASE_URL", ""),
        "SUPABASE_URL",
    )
    secret_key = _require_non_empty(
        os.environ.get("SUPABASE_SECRET_KEY", ""),
        "SUPABASE_SECRET_KEY",
    )
    queue_name = _default_queue_name()
    if not queue_name:
        raise RuntimeError(
            "SUPABASE_QUEUE_NAME must not be empty when set. "
            "Omit it to use default 'locations_jobs'."
        )

    return SupabaseConfig(
        url=url,
        secret_key=secret_key,
        queue_name=queue_name,
        table_platform_jobs=_default_table("platform_jobs", "platform_jobs"),
        table_pipeline_runs=_default_table("pipeline_runs", "pipeline_runs"),
        table_pipeline_run_events=_default_table(
            "pipeline_run_events", "pipeline_run_events"
        ),
        table_user_profiles=_default_table("user_profiles", "user_profiles"),
        table_invitation_codes=_default_table(
            "invitation_codes", "invitation_codes"
        ),
    )
