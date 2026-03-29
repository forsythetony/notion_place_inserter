"""Icon library: search, ingest metadata, and miss logging."""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from typing import Any

from loguru import logger
from supabase import AsyncClient

from app.repositories.icon_catalog_repository import IconCatalogRepository
from app.services.r2_media_storage_service import R2MediaStorageService


def normalize_icon_query(q: str) -> str:
    s = (q or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _svg_dimensions(svg: bytes) -> tuple[int | None, int | None]:
    """Best-effort width/height from SVG root (no full XML parse)."""
    try:
        head = svg[:200_000].decode("utf-8", errors="ignore")
    except Exception:
        return None, None
    m = re.search(
        r"<svg[^>]*\bwidth=\"([0-9.]+)(?:px)?\"",
        head,
        re.IGNORECASE | re.DOTALL,
    )
    m2 = re.search(
        r"<svg[^>]*\bheight=\"([0-9.]+)(?:px)?\"",
        head,
        re.IGNORECASE | re.DOTALL,
    )
    w = int(float(m.group(1))) if m else None
    h = int(float(m2.group(1))) if m2 else None
    return w, h


class IconCatalogService:
    """Shared by admin routes and runtime step."""

    def __init__(
        self,
        client: AsyncClient,
        storage: R2MediaStorageService | None,
    ) -> None:
        self._sb = client
        self._repo = IconCatalogRepository(client)
        self._storage = storage

    @property
    def storage(self) -> R2MediaStorageService | None:
        return self._storage

    async def search_icons(
        self,
        query: str,
        *,
        color_style: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        nq = normalize_icon_query(query)
        if not nq:
            return []
        raw = await self._repo.search_ranked_icons(
            normalized_query=nq,
            color_style=color_style,
            limit=limit,
        )
        out: list[dict[str, Any]] = []
        for row in raw:
            a = row["asset"]
            out.append(
                {
                    "icon_asset_id": str(a["id"]),
                    "title": a.get("title"),
                    "public_url": a.get("public_url"),
                    "color_style": a.get("color_style"),
                    "score": row["score"],
                    "matched_tags": row["matched_tags"],
                }
            )
        return out

    async def record_miss(
        self,
        *,
        raw_query: str,
        requested_color_style: str | None,
        source: str,
        job_id: str | None,
        job_run_id: str | None,
        step_id: str | None,
        example_context: dict[str, Any] | None = None,
    ) -> None:
        nq = normalize_icon_query(raw_query)
        if not nq:
            return
        await self._repo.upsert_search_miss(
            normalized_query=nq,
            raw_query=raw_query,
            requested_color_style=requested_color_style,
            source=source,
            job_id=job_id,
            job_run_id=job_run_id,
            step_id=step_id,
            example_context=example_context,
        )

    async def create_icon_from_upload(
        self,
        *,
        file_bytes: bytes,
        file_name: str,
        title: str,
        description: str | None,
        color_style: str,
        tags: list[dict[str, Any]],
        created_by_user_id: str | None,
    ) -> dict[str, Any]:
        if self._storage is None:
            raise RuntimeError("R2 storage is not configured")
        if len(file_bytes) > 2_000_000:
            raise ValueError("SVG file too large (max 2MB)")
        ct = "image/svg+xml"
        if not file_bytes.strip().startswith(b"<") or b"<svg" not in file_bytes[:2000].lower():
            raise ValueError("File is not a valid SVG")
        checksum = _sha256_bytes(file_bytes)
        dup = (
            await self._sb.table("icon_assets")
            .select("id, status")
            .eq("checksum_sha256", checksum)
            .in_("status", ["active", "draft"])
            .limit(1)
            .execute()
        )
        if dup.data:
            raise ValueError("An active icon with the same checksum already exists")
        asset_id = str(uuid.uuid4())
        ext = "svg"
        storage_key = self._storage.prefixed_object_key(f"icons/{asset_id}/original.{ext}")
        w, h = _svg_dimensions(file_bytes)
        bucket = __import__("os").environ.get("R2_BUCKET_NAME", "media")
        await asyncio.to_thread(
            lambda: self._storage.put_object(
                key=storage_key, body=file_bytes, content_type=ct
            )
        )
        public_url = self._storage.public_url_for_key(storage_key)
        row = {
            "id": asset_id,
            "title": title,
            "description": description,
            "file_name": file_name,
            "file_type": ct,
            "file_extension": ext,
            "file_size_bytes": len(file_bytes),
            "width": w,
            "height": h,
            "color_style": color_style,
            "storage_provider": "cloudflare_r2",
            "storage_bucket": bucket,
            "storage_key": storage_key,
            "public_url": public_url,
            "checksum_sha256": checksum,
            "status": "active",
            "created_by_user_id": created_by_user_id,
        }
        asset = await self._repo.insert_asset(row)
        await self._apply_tags(asset_id, tags)
        return await self.get_icon_detail(asset_id)

    async def replace_tags(self, asset_id: str, tags: list[dict[str, Any]]) -> None:
        """Replace all tag associations for an asset (authoritative list)."""
        await self._apply_tags(asset_id, tags)

    async def _apply_tags(self, asset_id: str, tags: list[dict[str, Any]]) -> None:
        tag_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for t in tags:
            label = str(t.get("label", "")).strip()
            if not label:
                continue
            nl = normalize_icon_query(label)
            if not nl or nl in seen:
                continue
            seen.add(nl)
            tid = await self._repo.upsert_tag(label=label, normalized_label=nl)
            strength = float(t.get("associationStrength", t.get("association_strength", 1.0)))
            is_primary = bool(t.get("isPrimary", t.get("is_primary", False)))
            tag_rows.append(
                {
                    "icon_asset_id": asset_id,
                    "icon_tag_id": tid,
                    "association_strength": strength,
                    "is_primary": is_primary,
                }
            )
        await self._repo.replace_asset_tags(icon_asset_id=asset_id, tag_rows=tag_rows)

    async def get_icon_detail(self, asset_id: str) -> dict[str, Any]:
        a = await self._repo.get_asset(asset_id)
        if not a:
            raise KeyError(asset_id)
        tags_map = await self._repo.list_tags_for_assets([str(a["id"])])
        tags = tags_map.get(str(a["id"]), [])
        return {"asset": a, "tags": tags}

    async def archive_icon(self, asset_id: str) -> dict[str, Any]:
        a = await self._repo.get_asset(asset_id)
        if not a:
            raise KeyError(asset_id)
        if self._storage and a.get("storage_key"):
            try:
                await asyncio.to_thread(
                    lambda k=str(a["storage_key"]): self._storage.delete_object(key=k)
                )
            except Exception as e:
                logger.exception("icon_archive_r2_delete_failed | asset_id={} error={}", asset_id, e)
                raise
        await self._repo.update_asset(
            asset_id,
            {"status": "archived", "public_url": None},
        )
        return (await self.get_icon_detail(asset_id))["asset"]

    async def reactivate_icon(
        self,
        asset_id: str,
        *,
        file_bytes: bytes,
        file_name: str,
    ) -> dict[str, Any]:
        if self._storage is None:
            raise RuntimeError("R2 storage is not configured")
        a = await self._repo.get_asset(asset_id)
        if not a or a.get("status") != "archived":
            raise ValueError("Can only reactivate archived icons")
        ct = "image/svg+xml"
        if not file_bytes.strip().startswith(b"<") or b"<svg" not in file_bytes[:2000].lower():
            raise ValueError("File is not a valid SVG")
        checksum = _sha256_bytes(file_bytes)
        dup = (
            await self._sb.table("icon_assets")
            .select("id")
            .eq("checksum_sha256", checksum)
            .in_("status", ["active", "draft"])
            .neq("id", asset_id)
            .limit(1)
            .execute()
        )
        if dup.data:
            raise ValueError("Another active icon has the same checksum")
        storage_key = self._storage.prefixed_object_key(f"icons/{asset_id}/original.svg")
        w, h = _svg_dimensions(file_bytes)
        bucket = __import__("os").environ.get("R2_BUCKET_NAME", "media")
        await asyncio.to_thread(
            lambda: self._storage.put_object(
                key=storage_key, body=file_bytes, content_type=ct
            )
        )
        public_url = self._storage.public_url_for_key(storage_key)
        await self._repo.update_asset(
            asset_id,
            {
                "file_name": file_name,
                "file_size_bytes": len(file_bytes),
                "width": w,
                "height": h,
                "storage_key": storage_key,
                "public_url": public_url,
                "checksum_sha256": checksum,
                "status": "active",
                "storage_bucket": bucket,
            },
        )
        return await self.get_icon_detail(asset_id)

    async def list_misses(
        self,
        *,
        resolved: bool | None = None,
        query: str | None = None,
        source: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return await self._repo.list_misses(
            resolved=resolved,
            query=query,
            source=source,
            limit=limit,
            offset=offset,
        )

    async def update_miss_row(self, miss_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        return await self._repo.update_miss(miss_id, patch)

    async def patch_asset_fields(self, asset_id: str, patch: dict[str, Any]) -> None:
        await self._repo.update_asset(asset_id, patch)

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
        return await self._repo.list_assets(
            query=query,
            tag_normalized=tag_normalized,
            color_style=color_style,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def list_tags_for_asset_ids(self, asset_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        return await self._repo.list_tags_for_assets(asset_ids)
