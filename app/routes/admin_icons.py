"""Admin routes for first-party icon library (SVG catalog + R2)."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.dependencies import AuthContext, require_admin_managed_auth
from app.services.icon_catalog_service import IconCatalogService

router = APIRouter(prefix="/auth/admin/icons", tags=["auth", "admin", "icons"])


def _svc(request: Request) -> IconCatalogService:
    svc = getattr(request.app.state, "icon_catalog_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Icon catalog service unavailable")
    return svc


def _asset_camel(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(a["id"]),
        "title": a.get("title"),
        "description": a.get("description"),
        "fileName": a.get("file_name"),
        "fileType": a.get("file_type"),
        "fileExtension": a.get("file_extension"),
        "fileSizeBytes": a.get("file_size_bytes"),
        "width": a.get("width"),
        "height": a.get("height"),
        "colorStyle": a.get("color_style"),
        "storageProvider": a.get("storage_provider"),
        "storageBucket": a.get("storage_bucket"),
        "storageKey": a.get("storage_key"),
        "publicUrl": a.get("public_url"),
        "checksumSha256": a.get("checksum_sha256"),
        "status": a.get("status"),
        "createdByUserId": str(a["created_by_user_id"]) if a.get("created_by_user_id") else None,
        "createdAt": a.get("created_at"),
        "updatedAt": a.get("updated_at"),
    }


class IconTagIn(BaseModel):
    label: str
    association_strength: float = Field(default=1.0, ge=0.0, le=1.0)
    is_primary: bool = False


class IconPatchBody(BaseModel):
    title: str | None = None
    description: str | None = None
    color_style: str | None = None
    status: str | None = None
    tags: list[IconTagIn] | None = None


@router.get("/search")
async def admin_icon_search_preview(
    request: Request,
    query: str = Query(...),
    color_style: str | None = Query(None, alias="colorStyle"),
    limit: int = Query(20, ge=1, le=100),
    _auth: AuthContext = Depends(require_admin_managed_auth),
):
    svc = _svc(request)
    items = await svc.search_icons(query, color_style=color_style, limit=limit)
    return {"items": items}


@router.get("/misses")
async def admin_icon_misses(
    request: Request,
    resolved: bool | None = Query(None),
    query: str | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _auth: AuthContext = Depends(require_admin_managed_auth),
):
    svc = _svc(request)
    rows = await svc.list_misses(
        resolved=resolved, query=query, source=source, limit=limit, offset=offset
    )
    return {"items": rows}


@router.patch("/misses/{miss_id}")
async def admin_icon_miss_patch(
    request: Request,
    miss_id: str,
    body: dict[str, Any],
    _auth: AuthContext = Depends(require_admin_managed_auth),
):
    svc = _svc(request)
    allowed = {k: v for k, v in body.items() if k in ("resolved", "raw_query", "example_context")}
    if not allowed:
        raise HTTPException(status_code=400, detail="No valid fields to patch")
    row = await svc.update_miss_row(miss_id, allowed)
    if not row:
        raise HTTPException(status_code=404, detail="Miss not found")
    return row


@router.get("")
async def admin_icon_list(
    request: Request,
    query: str | None = Query(None),
    tag: str | None = Query(None),
    color_style: str | None = Query(None, alias="colorStyle"),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(require_admin_managed_auth),
):
    svc = _svc(request)
    rows = await svc.list_assets(
        query=query,
        tag_normalized=tag,
        color_style=color_style,
        status=status,
        limit=limit,
        offset=offset,
    )
    ids = [str(r["id"]) for r in rows]
    tags_map = await svc.list_tags_for_asset_ids(ids)
    out = []
    for r in rows:
        d = _asset_camel(r)
        d["tags"] = tags_map.get(str(r["id"]), [])
        out.append(d)
    return {"items": out}


@router.post("")
async def admin_icon_create(
    request: Request,
    auth: AuthContext = Depends(require_admin_managed_auth),
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str | None = Form(None),
    colorStyle: str = Form(...),
    tagsJson: str = Form("[]"),
):
    svc = _svc(request)
    raw = await file.read()
    try:
        tags_raw = json.loads(tagsJson) if tagsJson else []
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid tags JSON: {e}") from e
    tags: list[dict[str, Any]] = []
    for t in tags_raw:
        if isinstance(t, dict):
            tags.append(
                {
                    "label": t.get("label", ""),
                    "associationStrength": float(t.get("associationStrength", 1.0)),
                    "isPrimary": bool(t.get("isPrimary", False)),
                }
            )
    try:
        detail = await svc.create_icon_from_upload(
            file_bytes=raw,
            file_name=file.filename or "icon.svg",
            title=title,
            description=description,
            color_style=colorStyle,
            tags=tags,
            created_by_user_id=auth.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    a = detail["asset"]
    payload = _asset_camel(a)
    payload["tags"] = detail["tags"]
    return payload


@router.post("/bulk")
async def admin_icon_bulk(
    request: Request,
    auth: AuthContext = Depends(require_admin_managed_auth),
    archive: UploadFile = File(...),
    manifestJson: str = Form(...),
):
    svc = _svc(request)
    try:
        manifest = json.loads(manifestJson)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid manifest JSON: {e}") from e
    if not isinstance(manifest, list):
        raise HTTPException(status_code=400, detail="manifestJson must be a JSON array")
    zdata = await archive.read()
    results: list[dict[str, Any]] = []
    try:
        zf = zipfile.ZipFile(BytesIO(zdata))
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="Invalid zip archive") from e
    with zf:
        for i, entry in enumerate(manifest):
            if not isinstance(entry, dict):
                results.append({"index": i, "ok": False, "error": "manifest entry must be object"})
                continue
            fn = entry.get("fileName") or entry.get("file_name")
            title = entry.get("title") or "Untitled"
            cs = entry.get("colorStyle") or entry.get("color_style") or "light"
            tag_list = entry.get("tags") or []
            if not fn:
                results.append({"index": i, "ok": False, "error": "missing fileName"})
                continue
            try:
                svg_bytes = zf.read(fn)
            except KeyError:
                results.append({"index": i, "ok": False, "error": f"file not in zip: {fn}"})
                continue
            tags: list[dict[str, Any]] = []
            for t in tag_list:
                if isinstance(t, dict):
                    tags.append(
                        {
                            "label": t.get("label", ""),
                            "associationStrength": float(t.get("associationStrength", 1.0)),
                            "isPrimary": bool(t.get("isPrimary", False)),
                        }
                    )
            try:
                detail = await svc.create_icon_from_upload(
                    file_bytes=svg_bytes,
                    file_name=str(fn),
                    title=str(title),
                    description=entry.get("description"),
                    color_style=str(cs),
                    tags=tags,
                    created_by_user_id=auth.user_id,
                )
                results.append(
                    {"index": i, "ok": True, "iconId": str(detail["asset"]["id"])}
                )
            except Exception as e:
                results.append({"index": i, "ok": False, "error": str(e)})
    return {"results": results}


@router.get("/{icon_id}")
async def admin_icon_get(
    request: Request,
    icon_id: str,
    _auth: AuthContext = Depends(require_admin_managed_auth),
):
    svc = _svc(request)
    try:
        detail = await svc.get_icon_detail(icon_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Icon not found") from None
    a = detail["asset"]
    payload = _asset_camel(a)
    payload["tags"] = detail["tags"]
    return payload


@router.patch("/{icon_id}")
async def admin_icon_patch(
    request: Request,
    icon_id: str,
    body: IconPatchBody,
    _auth: AuthContext = Depends(require_admin_managed_auth),
):
    svc = _svc(request)
    if body.status == "archived":
        try:
            await svc.archive_icon(icon_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Icon not found") from None
        detail = await svc.get_icon_detail(icon_id)
        a = detail["asset"]
        payload = _asset_camel(a)
        payload["tags"] = detail["tags"]
        return payload
    patch: dict[str, Any] = {}
    if body.title is not None:
        patch["title"] = body.title
    if body.description is not None:
        patch["description"] = body.description
    if body.color_style is not None:
        patch["color_style"] = body.color_style
    if patch:
        await svc.patch_asset_fields(icon_id, patch)
    if body.tags is not None:
        tag_dicts = [
            {
                "label": t.label,
                "associationStrength": t.association_strength,
                "isPrimary": t.is_primary,
            }
            for t in body.tags
        ]
        await svc.replace_tags(icon_id, tag_dicts)
    detail = await svc.get_icon_detail(icon_id)
    a = detail["asset"]
    payload = _asset_camel(a)
    payload["tags"] = detail["tags"]
    return payload


@router.post("/{icon_id}/reactivate")
async def admin_icon_reactivate(
    request: Request,
    icon_id: str,
    auth: AuthContext = Depends(require_admin_managed_auth),
    file: UploadFile = File(...),
):
    svc = _svc(request)
    raw = await file.read()
    try:
        detail = await svc.reactivate_icon(
            icon_id, file_bytes=raw, file_name=file.filename or "icon.svg"
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Icon not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    a = detail["asset"]
    payload = _asset_camel(a)
    payload["tags"] = detail["tags"]
    return payload
