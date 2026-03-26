"""Persistence for beta waitlist submissions (Supabase / PostgREST)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from supabase import AsyncClient

from app.integrations.supabase_config import SupabaseConfig


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseBetaWaitlistRepository:
    """Insert / update waitlist rows keyed by email_normalized."""

    def __init__(self, client: AsyncClient, config: SupabaseConfig) -> None:
        self._client = client
        self._config = config

    @property
    def _table(self) -> str:
        return self._config.table_beta_waitlist_submissions

    async def get_by_email_normalized(self, email_normalized: str) -> dict[str, Any] | None:
        try:
            resp = await (
                self._client.table(self._table)
                .select("*")
                .eq("email_normalized", email_normalized)
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception("waitlist_get_by_email_failed")
            raise
        data = resp.data
        if not data or (isinstance(data, list) and len(data) == 0):
            return None
        row = data[0] if isinstance(data, list) else data
        return dict(row) if isinstance(row, dict) else None

    async def insert_submission(self, row: dict[str, Any]) -> None:
        try:
            await self._client.table(self._table).insert(row).execute()
        except Exception:
            logger.exception("waitlist_insert_failed")
            raise

    async def update_resubmission(self, row_id: str, row: dict[str, Any]) -> None:
        try:
            await self._client.table(self._table).update(row).eq("id", row_id).execute()
        except Exception:
            logger.exception("waitlist_update_failed")
            raise
