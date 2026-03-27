"""Persistence for beta waitlist submissions (Supabase / PostgREST)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from loguru import logger
from supabase import AsyncClient

from app.integrations.supabase_config import SupabaseConfig


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_ilike_term(raw: str) -> str:
    """Strip characters that break PostgREST `or` / `ilike` filter strings."""
    return re.sub(r"[%_,]", " ", raw).strip()


WAITLIST_ADMIN_SORTS = frozenset(
    {
        "last_submitted_at_desc",
        "last_submitted_at_asc",
        "created_at_desc",
        "created_at_asc",
    }
)

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

    async def get_by_id(self, row_id: str | UUID) -> dict[str, Any] | None:
        rid = str(row_id) if isinstance(row_id, UUID) else row_id
        try:
            resp = await (
                self._client.table(self._table).select("*").eq("id", rid).limit(1).execute()
            )
        except Exception:
            logger.exception("waitlist_admin_get_by_id_failed")
            raise
        data = resp.data
        if not data or (isinstance(data, list) and len(data) == 0):
            return None
        row = data[0] if isinstance(data, list) else data
        if not isinstance(row, dict):
            return None
        d = dict(row)
        wid = d.get("beta_wave_id")
        if wid:
            keys = await self._beta_wave_keys_by_id([str(wid)])
            d["beta_wave_key"] = keys.get(str(wid))
        else:
            d["beta_wave_key"] = None
        return d

    async def list_for_admin(
        self,
        *,
        q: str | None = None,
        statuses: list[str] | None = None,
        beta_wave_id: str | None = None,
        heard_about: str | None = None,
        invited: bool | None = None,
        sort: str = "last_submitted_at_desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], bool]:
        """
        Server-backed waitlist listing. Returns (rows, has_more).
        """
        lim = max(1, min(limit, 200))
        off = max(0, offset)
        sort_key = sort if sort in WAITLIST_ADMIN_SORTS else "last_submitted_at_desc"
        ascending = sort_key.endswith("_asc")
        if "created_at" in sort_key:
            order_col = "created_at"
        else:
            order_col = "last_submitted_at"

        try:
            qb = self._client.table(self._table).select("*")
            if statuses:
                qb = qb.in_("status", statuses)
            if beta_wave_id:
                qb = qb.eq("beta_wave_id", beta_wave_id)
            if heard_about and heard_about.strip():
                qb = qb.eq("heard_about", heard_about.strip())
            if invited is True:
                qb = qb.not_.is_("invitation_code_id", "null")
            if invited is False:
                qb = qb.is_("invitation_code_id", "null")
            if q and q.strip():
                t = _sanitize_ilike_term(q.strip())
                if t:
                    pat = f"%{t}%"
                    qb = qb.or_(
                        f"email.ilike.{pat},email_normalized.ilike.{pat},"
                        f"name.ilike.{pat},notion_use_case.ilike.{pat}"
                    )
            qb = qb.order(order_col, desc=not ascending).order("id", desc=not ascending)
            # Request lim+1 rows to detect has_more; Range is inclusive (off .. off+lim).
            qb = qb.range(off, off + lim)
            resp = await qb.execute()
        except Exception:
            logger.exception("waitlist_admin_list_failed")
            raise

        rows = [dict(r) for r in list(resp.data or []) if isinstance(r, dict)]
        has_more = len(rows) > lim
        if has_more:
            rows = rows[:lim]
        wave_ids = {r.get("beta_wave_id") for r in rows if r.get("beta_wave_id")}
        wave_keys = await self._beta_wave_keys_by_id(
            [str(x) for x in wave_ids if x is not None]
        )
        for r in rows:
            wid = r.get("beta_wave_id")
            r["beta_wave_key"] = wave_keys.get(str(wid)) if wid else None
        return rows, has_more

    async def _beta_wave_keys_by_id(self, wave_ids: list[str]) -> dict[str, str]:
        if not wave_ids:
            return {}
        try:
            resp = await (
                self._client.table(self._config.table_beta_waves)
                .select("id, key")
                .in_("id", wave_ids)
                .execute()
            )
        except Exception:
            logger.exception("waitlist_admin_wave_keys_lookup_failed")
            raise
        out: dict[str, str] = {}
        for c in resp.data or []:
            if isinstance(c, dict) and c.get("id") is not None:
                out[str(c["id"])] = str(c["key"])
        return out

    async def patch_submission_admin(
        self,
        row_id: str | UUID,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Apply partial updates (keys: admin_notes, beta_wave_id, status, reviewed_at)."""
        rid = str(row_id) if isinstance(row_id, UUID) else row_id
        allowed = frozenset({"admin_notes", "beta_wave_id", "status", "reviewed_at"})
        fields: dict[str, Any] = {}
        for k, v in updates.items():
            if k not in allowed:
                continue
            if k == "beta_wave_id":
                if v is None:
                    fields[k] = None
                else:
                    fields[k] = str(v) if not isinstance(v, UUID) else str(v)
            else:
                fields[k] = v
        if not fields:
            return await self.get_by_id(rid)
        payload = {**fields, "updated_at": _utc_now_iso()}
        try:
            await self._client.table(self._table).update(payload).eq("id", rid).execute()
        except Exception:
            logger.exception("waitlist_admin_patch_failed")
            raise
        return await self.get_by_id(rid)

    async def link_invitation_to_submission(
        self,
        row_id: str | UUID,
        invitation_code_id: str | UUID,
        *,
        invited_at_iso: str | None = None,
        beta_wave_id: str | UUID | None = None,
    ) -> dict[str, Any] | None:
        """Set invitation handoff fields after issuing from waitlist."""
        rid = str(row_id) if isinstance(row_id, UUID) else row_id
        iid = (
            str(invitation_code_id)
            if isinstance(invitation_code_id, UUID)
            else invitation_code_id
        )
        payload: dict[str, Any] = {
            "invitation_code_id": iid,
            "invited_at": invited_at_iso or _utc_now_iso(),
            "status": "INVITED",
            "updated_at": _utc_now_iso(),
        }
        if beta_wave_id is not None:
            payload["beta_wave_id"] = (
                str(beta_wave_id)
                if isinstance(beta_wave_id, UUID)
                else beta_wave_id
            )
        try:
            await self._client.table(self._table).update(payload).eq("id", rid).execute()
        except Exception:
            logger.exception("waitlist_admin_link_invite_failed")
            raise
        return await self.get_by_id(rid)
