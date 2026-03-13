"""Backend integrations (Supabase, etc.)."""

from app.integrations.supabase_config import SupabaseConfig, load_supabase_config

__all__ = [
    "SupabaseConfig",
    "load_supabase_config",
]
