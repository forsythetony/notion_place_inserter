"""Supabase client factory for backend trusted contexts."""

from typing import Any

from supabase import Client, create_client

from app.integrations.supabase_config import SupabaseConfig


def create_supabase_client(config: SupabaseConfig) -> Client:
    """
    Create a Supabase client for backend use (service role / secret key).
    Use only in trusted server contexts (FastAPI, worker, scripts).
    """
    return create_client(
        supabase_url=config.url,
        supabase_key=config.secret_key,
    )


def get_supabase_client_from_app(app: Any) -> Client | None:
    """
    Retrieve the Supabase client from app.state if set.
    Returns None when Supabase is not configured (e.g. startup failed).
    """
    return getattr(app.state, "supabase_client", None)
