"""Postgres access for icon library tables (Supabase service client)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from supabase import AsyncClient


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IconCatalogRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def find_tag_ids_by_normalized_label(self, normalized_label: str) -> list[str]:
        r = await (
            self._client.table("icon_tags")
            .select("id")
            .eq("normalized_label", normalized_label)
            .execute()
        )
        rows = r.data or []
        return [str(row["id"]) for row in rows]

    async def upsert_tag(
        self,
        *,
        label: str,
        normalized_label: str,
        canonical_tag_id: str | None = None,
    ) -> str:
        """Insert tag if missing; return id (by normalized_label)."""
        existing = await (
            self._client.table("icon_tags")
            .select("id")
            .eq("normalized_label", normalized_label)
            .limit(1)
            .execute()
        )
        if existing.data:
            return str(existing.data[0]["id"])
        row = {
            "id": str(uuid.uuid4()),
            "label": label,
            "normalized_label": normalized_label,
            "canonical_tag_id": canonical_tag_id,
            "updated_at": _utc_now_iso(),
        }
        ins = await self._client.table("icon_tags").insert(row).execute()
        if ins.data:
            return str(ins.data[0]["id"])
        logger.warning("icon_tag_insert_no_data | normalized_label={}", normalized_label)
        again = await (
            self._client.table("icon_tags")
            .select("id")
            .eq("normalized_label", normalized_label)
            .limit(1)
            .execute()
        )
        if again.data:
            return str(again.data[0]["id"])
        raise RuntimeError("Failed to upsert icon tag")

    async def insert_asset(
        self,
        row: dict[str, Any],
    ) -> dict[str, Any]:
        row.setdefault("id", str(uuid.uuid4()))
        row["updated_at"] = _utc_now_iso()
        ins = await self._client.table("icon_assets").insert(row).execute()
        if not ins.data:
            raise RuntimeError("icon_assets insert returned no data")
        return ins.data[0]

    async def replace_asset_tags(
        self,
        *,
        icon_asset_id: str,
        tag_rows: list[dict[str, Any]],
    ) -> None:
        await (
            self._client.table("icon_asset_tags")
            .delete()
            .eq("icon_asset_id", icon_asset_id)
            .execute()
        )
        if not tag_rows:
            return
        await self._client.table("icon_asset_tags").insert(tag_rows).execute()

    async def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        r = await (
            self._client.table("icon_assets")
            .select("*")
            .eq("id", asset_id)
            .limit(1)
            .execute()
        )
        if not r.data:
            return None
        return r.data[0]

    async def list_assets(
        self,
        *,
        query: str | None = None,
        tag_normalized: str | None = None,
        color_style: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        q = self._client.table("icon_assets").select("*")
        if status is not None and status != "":
            q = q.eq("status", status)
        if color_style:
            q = q.eq("color_style", color_style)
        if query:
            q = q.ilike("title", f"%{query}%")
        q = q.order("updated_at", desc=True).range(offset, offset + max(limit - 1, 0))
        r = await q.execute()
        rows = list(r.data or [])
        if tag_normalized and rows:
            tag_ids = await self.find_tag_ids_by_normalized_label(tag_normalized)
            if not tag_ids:
                return []
            ar = await (
                self._client.table("icon_asset_tags")
                .select("icon_asset_id")
                .in_("icon_tag_id", tag_ids)
                .execute()
            )
            allowed = {str(x["icon_asset_id"]) for x in (ar.data or [])}
            rows = [x for x in rows if str(x["id"]) in allowed]
        return rows[:limit]

    async def list_tags_for_assets(self, asset_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not asset_ids:
            return {}
        r = await (
            self._client.table("icon_asset_tags")
            .select("icon_asset_id, association_strength, is_primary, icon_tag_id")
            .in_("icon_asset_id", asset_ids)
            .execute()
        )
        tag_ids = list({str(row["icon_tag_id"]) for row in (r.data or [])})
        labels: dict[str, dict[str, Any]] = {}
        if tag_ids:
            tr = await (
                self._client.table("icon_tags")
                .select("id, label, normalized_label")
                .in_("id", tag_ids)
                .execute()
            )
            for t in tr.data or []:
                labels[str(t["id"])] = t
        out: dict[str, list[dict[str, Any]]] = {}
        for row in r.data or []:
            aid = str(row["icon_asset_id"])
            tid = str(row["icon_tag_id"])
            tag = labels.get(tid) or {}
            out.setdefault(aid, []).append(
                {
                    "tagId": tid,
                    "label": tag.get("label"),
                    "normalizedLabel": tag.get("normalized_label"),
                    "associationStrength": float(row.get("association_strength", 0)),
                    "isPrimary": bool(row.get("is_primary")),
                }
            )
        return out

    async def update_asset(self, asset_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        patch = {**patch, "updated_at": _utc_now_iso()}
        r = await (
            self._client.table("icon_assets").update(patch).eq("id", asset_id).execute()
        )
        if r.data:
            return r.data[0]
        return await self.get_asset(asset_id)

    async def fetch_assets_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        r = await self._client.table("icon_assets").select("*").in_("id", ids).execute()
        return list(r.data or [])

    async def search_ranked_icons(
        self,
        *,
        normalized_query: str,
        color_style: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return list of {asset, score, matched_tags}."""
        tag_ids = await self.find_tag_ids_by_normalized_label(normalized_query)
        if not tag_ids:
            return []
        tr = await (
            self._client.table("icon_asset_tags")
            .select("icon_asset_id, association_strength, icon_tag_id")
            .in_("icon_tag_id", tag_ids)
            .execute()
        )
        rows = tr.data or []
        if not rows:
            return []
        all_tids = list({str(row["icon_tag_id"]) for row in rows})
        trows = await (
            self._client.table("icon_tags")
            .select("id, label, normalized_label")
            .in_("id", all_tids)
            .execute()
        )
        tag_map = {str(t["id"]): t for t in (trows.data or [])}
        by_asset: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            aid = str(row["icon_asset_id"])
            tid = str(row["icon_tag_id"])
            tag = tag_map.get(tid) or {}
            by_asset.setdefault(aid, []).append(
                {
                    "strength": float(row.get("association_strength", 0)),
                    "label": tag.get("label"),
                    "normalized_label": tag.get("normalized_label"),
                }
            )
        asset_ids = list(by_asset.keys())
        assets = await self.fetch_assets_by_ids(asset_ids)
        asset_map = {str(a["id"]): a for a in assets}
        results: list[dict[str, Any]] = []
        for aid, matches in by_asset.items():
            a = asset_map.get(aid)
            if not a or a.get("status") != "active":
                continue
            if color_style and a.get("color_style") != color_style:
                continue
            if not a.get("public_url"):
                continue
            score = max(m["strength"] for m in matches)
            matched_tags = [
                {
                    "label": m["label"],
                    "normalizedLabel": m["normalized_label"],
                    "weight": m["strength"],
                }
                for m in matches
            ]
            results.append({"asset": a, "score": score, "matched_tags": matched_tags})
        results.sort(
            key=lambda x: (
                -x["score"],
                str(x["asset"].get("updated_at") or ""),
                str(x["asset"].get("title") or ""),
            )
        )
        return results[:limit]

    async def upsert_search_miss(
        self,
        *,
        normalized_query: str,
        raw_query: str,
        requested_color_style: str | None,
        source: str,
        job_id: str | None,
        job_run_id: str | None,
        step_id: str | None,
        example_context: dict[str, Any] | None,
    ) -> None:
        sel = (
            self._client.table("icon_search_misses")
            .select("id, miss_count")
            .eq("normalized_query", normalized_query)
            .eq("source", source)
        )
        if requested_color_style is None:
            sel = sel.is_("requested_color_style", "null")
        else:
            sel = sel.eq("requested_color_style", requested_color_style)
        if step_id is None:
            sel = sel.is_("step_id", "null")
        else:
            sel = sel.eq("step_id", step_id)
        r = await sel.limit(1).execute()
        now = _utc_now_iso()
        if r.data:
            mid = r.data[0]["id"]
            mc = int(r.data[0].get("miss_count") or 1) + 1
            await (
                self._client.table("icon_search_misses")
                .update({"miss_count": mc, "last_seen_at": now, "raw_query": raw_query})
                .eq("id", mid)
                .execute()
            )
            return
        row = {
            "id": str(uuid.uuid4()),
            "normalized_query": normalized_query,
            "raw_query": raw_query,
            "requested_color_style": requested_color_style,
            "source": source,
            "job_id": job_id,
            "job_run_id": job_run_id,
            "step_id": step_id,
            "miss_count": 1,
            "first_seen_at": now,
            "last_seen_at": now,
            "example_context": example_context,
            "resolved": False,
        }
        await self._client.table("icon_search_misses").insert(row).execute()

    async def list_misses(
        self,
        *,
        resolved: bool | None = None,
        query: str | None = None,
        source: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        q = self._client.table("icon_search_misses").select("*")
        if resolved is not None:
            q = q.eq("resolved", resolved)
        if source:
            q = q.eq("source", source)
        if query:
            q = q.ilike("normalized_query", f"%{query}%")
        q = q.order("miss_count", desc=True).order("last_seen_at", desc=True)
        q = q.range(offset, offset + max(limit - 1, 0))
        r = await q.execute()
        return list(r.data or [])

    async def update_miss(self, miss_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        r = await (
            self._client.table("icon_search_misses")
            .update(patch)
            .eq("id", miss_id)
            .execute()
        )
        if r.data:
            return r.data[0]
        return None
