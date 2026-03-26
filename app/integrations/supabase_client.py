"""Supabase async client factory for backend trusted contexts."""

from typing import Any

from supabase import AsyncClient, acreate_client

from app.integrations.supabase_config import SupabaseConfig


async def create_async_supabase_client(config: SupabaseConfig) -> AsyncClient:
    """
    Create an async Supabase client for backend use (service role / secret key).
    Use only in trusted server contexts (FastAPI, worker, scripts).
    """
    return await acreate_client(
        supabase_url=config.url,
        supabase_key=config.secret_key,
    )


def get_supabase_client_from_app(app: Any) -> AsyncClient | None:
    """
    Retrieve the Supabase client from app.state if set.
    Returns None when Supabase is not configured (e.g. startup failed).
    """
    return getattr(app.state, "supabase_client", None)
