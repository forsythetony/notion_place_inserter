"""Admin-only auth directory: user profiles and cohorts."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import AuthContext, require_admin_managed_auth
from app.services.supabase_auth_repository import SupabaseAuthRepository

router = APIRouter(prefix="/auth/admin", tags=["auth", "admin"])


def _cohort_row_to_item(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "key": row["key"],
        "description": row.get("description"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }


def _profile_row_to_item(row: dict) -> dict:
    return {
        "userId": str(row["user_id"]),
        "userType": row["user_type"],
        "email": row.get("email"),
        "invitationCodeId": str(row["invitation_code_id"])
        if row.get("invitation_code_id")
        else None,
        "cohortId": str(row["cohort_id"]) if row.get("cohort_id") else None,
        "cohortKey": row.get("cohort_key"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }


@router.get("/user-profiles")
def list_user_profiles_admin(
    request: Request,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    logger.info(
        "admin_list_user_profiles | admin_user_id={}",
        ctx.user_id,
    )
    rows = auth_repo.list_user_profiles_for_admin()
    return {"items": [_profile_row_to_item(r) for r in rows]}


class CohortCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str = Field(..., min_length=1)
    description: str | None = None


class CohortPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None


@router.get("/cohorts")
def list_cohorts_admin(
    request: Request,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    logger.info("admin_list_cohorts | admin_user_id={}", ctx.user_id)
    rows = auth_repo.list_cohorts()
    return {"items": [_cohort_row_to_item(r) for r in rows]}


@router.post("/cohorts", status_code=201)
def create_cohort_admin(
    request: Request,
    body: CohortCreateRequest,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    if auth_repo.get_cohort_by_key(body.key):
        raise HTTPException(
            status_code=409,
            detail="A cohort with this key already exists",
        )
    try:
        row = auth_repo.create_cohort(body.key, body.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    logger.info(
        "admin_create_cohort | admin_user_id={} cohort_id={} cohort_key={}",
        ctx.user_id,
        row.get("id"),
        row.get("key"),
    )
    return _cohort_row_to_item(row)


@router.patch("/cohorts/{cohort_id}")
def patch_cohort_admin(
    request: Request,
    cohort_id: UUID,
    body: CohortPatchRequest,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    updated = auth_repo.update_cohort_description(cohort_id, body.description)
    if updated is None:
        raise HTTPException(status_code=404, detail="Cohort not found")
    logger.info(
        "admin_patch_cohort | admin_user_id={} cohort_id={}",
        ctx.user_id,
        cohort_id,
    )
    return _cohort_row_to_item(updated)


@router.delete("/cohorts/{cohort_id}", status_code=204)
def delete_cohort_admin(
    request: Request,
    cohort_id: UUID,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    result = auth_repo.delete_cohort_if_unused(cohort_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Cohort not found")
    if result == "in_use":
        raise HTTPException(
            status_code=409,
            detail="Cannot delete cohort: still referenced by invitations or user profiles",
        )
    logger.info(
        "admin_delete_cohort | admin_user_id={} cohort_id={}",
        ctx.user_id,
        cohort_id,
    )
