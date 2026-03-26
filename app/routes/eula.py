"""Public current EULA and admin EULA version management."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.dependencies import AuthContext, require_admin_managed_auth
from app.services.supabase_auth_repository import SupabaseAuthRepository

public_router = APIRouter(prefix="/auth", tags=["auth"])
admin_router = APIRouter(prefix="/auth/admin", tags=["auth", "admin"])


def _eula_row_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "versionLabel": row["version_label"],
        "fullText": row["full_text"],
        "plainLanguageSummary": row.get("plain_language_summary"),
        "publishedAt": row.get("published_at"),
        "contentSha256": row.get("content_sha256"),
    }


def _eula_row_admin(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "status": row["status"],
        "versionLabel": row["version_label"],
        "fullText": row["full_text"],
        "plainLanguageSummary": row.get("plain_language_summary"),
        "contentSha256": row.get("content_sha256"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
        "publishedAt": row.get("published_at"),
        "createdByUserId": str(row["created_by_user_id"])
        if row.get("created_by_user_id")
        else None,
    }


@public_router.get("/eula/current")
async def get_current_eula(request: Request):
    """Return the published EULA for signup display (unauthenticated)."""
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    row = await auth_repo.get_published_eula()
    if row is None:
        raise HTTPException(status_code=404, detail="No published EULA")
    return _eula_row_public(row)


class EulaDraftCreateRequest(BaseModel):
    version_label: str = Field(..., min_length=1)
    full_text: str = Field(..., min_length=1)
    plain_language_summary: dict[str, Any]


class EulaDraftUpdateRequest(BaseModel):
    version_label: str | None = Field(default=None, min_length=1)
    full_text: str | None = Field(default=None, min_length=1)
    plain_language_summary: dict[str, Any] | None = None


class EulaCopyRequest(BaseModel):
    version_label: str = Field(..., min_length=1)


@admin_router.get("/eula/versions")
async def list_eula_versions_admin(
    request: Request,
    _ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    rows = await auth_repo.list_eula_versions_for_admin()
    return [_eula_row_admin(r) for r in rows]


@admin_router.post("/eula/versions")
async def create_eula_draft_admin(
    request: Request,
    body: EulaDraftCreateRequest,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    try:
        row = await auth_repo.insert_eula_draft(
            body.version_label,
            body.full_text,
            body.plain_language_summary,
            created_by_user_id=ctx.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        msg = str(e).lower()
        if "unique" in msg or "duplicate" in msg:
            raise HTTPException(
                status_code=400,
                detail="A version with this label already exists",
            ) from e
        raise
    return _eula_row_admin(row)


@admin_router.get("/eula/versions/{version_id}")
async def get_eula_version_admin(
    request: Request,
    version_id: UUID,
    _ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    row = await auth_repo.get_eula_version_by_id(version_id)
    if row is None:
        raise HTTPException(status_code=404, detail="EULA version not found")
    return _eula_row_admin(row)


@admin_router.patch("/eula/versions/{version_id}")
async def update_eula_draft_admin(
    request: Request,
    version_id: UUID,
    body: EulaDraftUpdateRequest,
    _ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    if (
        body.version_label is None
        and body.full_text is None
        and body.plain_language_summary is None
    ):
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        row = await auth_repo.update_eula_draft(
            version_id,
            version_label=body.version_label,
            full_text=body.full_text,
            plain_language_summary=body.plain_language_summary,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Draft not found or not a draft",
        )
    return _eula_row_admin(row)


@admin_router.post("/eula/versions/{version_id}/copy")
async def copy_eula_version_admin(
    request: Request,
    version_id: UUID,
    body: EulaCopyRequest,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    try:
        row = await auth_repo.copy_eula_to_new_draft(
            version_id,
            body.version_label,
            created_by_user_id=ctx.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        msg = str(e).lower()
        if "unique" in msg or "duplicate" in msg:
            raise HTTPException(
                status_code=400,
                detail="A version with this label already exists",
            ) from e
        raise
    return _eula_row_admin(row)


@admin_router.post("/eula/versions/{version_id}/publish")
async def publish_eula_version_admin(
    request: Request,
    version_id: UUID,
    _ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    row = await auth_repo.get_eula_version_by_id(version_id)
    if row is None:
        raise HTTPException(status_code=404, detail="EULA version not found")
    if row.get("status") != "draft":
        raise HTTPException(status_code=400, detail="Only a draft can be published")
    try:
        await auth_repo.publish_eula_version_rpc(version_id)
    except Exception as e:
        msg = str(e)
        if "not a draft" in msg.lower() or "publish_eula_version" in msg:
            raise HTTPException(status_code=400, detail=msg) from e
        raise
    out = await auth_repo.get_eula_version_by_id(version_id)
    if out is None:
        raise HTTPException(status_code=500, detail="Publish succeeded but row missing")
    return _eula_row_admin(out)
