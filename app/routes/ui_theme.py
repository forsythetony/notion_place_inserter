"""UI theme runtime and admin CRUD (p5 admin runtime theme)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import AuthContext, require_admin_managed_auth, require_managed_auth
from app.services.ui_theme_service import (
    parse_and_validate_stored_config,
    validate_config_json_size,
)

runtime_router = APIRouter(prefix="/theme", tags=["theme"])
admin_router = APIRouter(prefix="/management/ui-theme", tags=["management", "ui-theme"])


def _svc(request: Request):
    svc = getattr(request.app.state, "ui_theme_service", None)
    if svc is None:
        logger.error("ui_theme_service_missing")
        raise HTTPException(status_code=500, detail="Server misconfiguration")
    return svc


def _validation_422(errors: list[str]) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation failed", "validation_errors": errors},
    )


# --- Runtime ---


@runtime_router.get("/runtime")
async def get_theme_runtime(
    request: Request,
    _ctx: AuthContext = Depends(require_managed_auth),
):
    """Merged cssVars for the active preset (any authenticated user)."""
    return await _svc(request).get_runtime_payload()


# --- Admin request bodies ---


class CreatePresetBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    config: dict[str, Any]


class UpdatePresetBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    config: dict[str, Any] | None = None


class SetActiveBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    preset_id: str | None = Field(default=None, alias="presetId")


class DuplicatePresetBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class PreviewDerivedBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    base_config: dict[str, Any] = Field(alias="baseConfig")
    target: Literal["dark", "light"]


# --- Admin handlers ---


@admin_router.get("/presets")
async def list_presets(
    request: Request,
    _ctx: AuthContext = Depends(require_admin_managed_auth),
):
    repo = _svc(request)._repo
    rows = await repo.list_presets_metadata()
    return {
        "items": [
            {
                "id": r["id"],
                "name": r["name"],
                "isSystem": r["is_system"],
                "updatedAt": r["updated_at"].isoformat() if isinstance(r["updated_at"], datetime) else r["updated_at"],
            }
            for r in rows
        ]
    }


@admin_router.post("/presets")
async def create_preset(
    request: Request,
    body: CreatePresetBody,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    raw = body.config
    if isinstance(raw, dict):
        errs = validate_config_json_size(json.dumps(raw, separators=(",", ":")))
        if errs:
            return _validation_422(errs)
    _, verr = parse_and_validate_stored_config(raw)
    if verr:
        return _validation_422(verr)
    repo = _svc(request)._repo
    try:
        row = await repo.create_preset(
            body.name.strip(),
            raw,
            created_by_user_id=ctx.user_id,
        )
    except Exception as e:
        logger.exception("ui_theme_create_failed | error={}", e)
        raise HTTPException(status_code=500, detail="Failed to create preset") from e
    return _preset_response(row)


@admin_router.get("/presets/{preset_id}")
async def get_preset(
    request: Request,
    preset_id: str,
    _ctx: AuthContext = Depends(require_admin_managed_auth),
):
    row = await _svc(request)._repo.get_preset_by_id(preset_id)
    if not row:
        raise HTTPException(status_code=404, detail="Preset not found")
    return _preset_response(row)


@admin_router.put("/presets/{preset_id}")
async def update_preset(
    request: Request,
    preset_id: str,
    body: UpdatePresetBody,
    _ctx: AuthContext = Depends(require_admin_managed_auth),
):
    repo = _svc(request)._repo
    existing = await repo.get_preset_by_id(preset_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Preset not found")
    name = body.name
    config = body.config
    if config is not None:
        errs = validate_config_json_size(json.dumps(config, separators=(",", ":")))
        if errs:
            return _validation_422(errs)
        _, verr = parse_and_validate_stored_config(config)
        if verr:
            return _validation_422(verr)
    if name is None and config is None:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        row = await repo.update_preset(
            preset_id,
            name=name.strip() if name is not None else None,
            config=config,
        )
    except Exception as e:
        logger.exception("ui_theme_update_failed | error={}", e)
        raise HTTPException(status_code=500, detail="Failed to update preset") from e
    if not row:
        raise HTTPException(status_code=404, detail="Preset not found")
    return _preset_response(row)


@admin_router.delete("/presets/{preset_id}")
async def delete_preset(
    request: Request,
    preset_id: str,
    _ctx: AuthContext = Depends(require_admin_managed_auth),
):
    repo = _svc(request)._repo
    is_sys = await repo.get_preset_is_system(preset_id)
    if is_sys is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    if is_sys:
        raise HTTPException(status_code=403, detail="Cannot delete system preset")
    ok = await repo.delete_preset(preset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"ok": True}


@admin_router.post("/presets/{preset_id}/duplicate")
async def duplicate_preset(
    request: Request,
    preset_id: str,
    body: DuplicatePresetBody,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    repo = _svc(request)._repo
    row = await repo.duplicate_preset(
        preset_id,
        body.name.strip() if body.name else None,
        created_by_user_id=ctx.user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Preset not found")
    return _preset_response(row)


@admin_router.get("/active")
async def get_active(
    request: Request,
    _ctx: AuthContext = Depends(require_admin_managed_auth),
):
    return await _svc(request).get_active_for_admin()


@admin_router.put("/active")
async def set_active(
    request: Request,
    body: SetActiveBody,
    _ctx: AuthContext = Depends(require_admin_managed_auth),
):
    repo = _svc(request)._repo
    pid = body.preset_id
    if pid is not None:
        if not await repo.get_preset_by_id(pid):
            raise HTTPException(status_code=404, detail="Preset not found")
    await repo.set_active_preset_id(pid)
    return await _svc(request).get_active_for_admin()


@admin_router.post("/actions/preview-derived")
async def preview_derived(
    request: Request,
    body: PreviewDerivedBody,
    _ctx: AuthContext = Depends(require_admin_managed_auth),
):
    try:
        cfg = _svc(request).preview_derived_config(body.base_config, body.target)
    except ValueError as e:
        return _validation_422([str(e)])
    return {"config": cfg}


def _preset_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "config": row["config"],
        "isSystem": row["is_system"],
        "createdAt": row["created_at"].isoformat() if row.get("created_at") else None,
        "updatedAt": row["updated_at"].isoformat() if row.get("updated_at") else None,
        "createdByUserId": row.get("created_by_user_id"),
    }
