"""Admin-only auth directory: user profiles and cohorts."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import AuthContext, require_admin_managed_auth
from app.domain.limits import AppLimits
from app.services.effective_limits import (
    LimitsResolutionError,
    limits_resolution_summary,
    resolve_effective_app_limits,
)
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


def _limits_row_snake(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "max_stages_per_job": row.get("max_stages_per_job"),
        "max_pipelines_per_stage": row.get("max_pipelines_per_stage"),
        "max_steps_per_pipeline": row.get("max_steps_per_pipeline"),
        "max_jobs_per_owner": row.get("max_jobs_per_owner"),
        "max_triggers_per_owner": row.get("max_triggers_per_owner"),
        "max_runs_per_utc_day": row.get("max_runs_per_utc_day"),
        "max_runs_per_utc_month": row.get("max_runs_per_utc_month"),
    }


class AppLimitsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_stages_per_job: int = Field(..., gt=0)
    max_pipelines_per_stage: int = Field(..., gt=0)
    max_steps_per_pipeline: int = Field(..., gt=0)
    max_jobs_per_owner: int = Field(..., gt=0)
    max_triggers_per_owner: int = Field(..., gt=0)
    max_runs_per_utc_day: int = Field(..., gt=0)
    max_runs_per_utc_month: int = Field(..., gt=0)


def _app_limits_from_payload(body: AppLimitsPayload) -> AppLimits:
    return AppLimits(
        max_stages_per_job=body.max_stages_per_job,
        max_pipelines_per_stage=body.max_pipelines_per_stage,
        max_steps_per_pipeline=body.max_steps_per_pipeline,
        max_jobs_per_owner=body.max_jobs_per_owner,
        max_triggers_per_owner=body.max_triggers_per_owner,
        max_runs_per_utc_day=body.max_runs_per_utc_day,
        max_runs_per_utc_month=body.max_runs_per_utc_month,
    )


def _app_config_repo_or_501(request: Request):
    repo = getattr(request.app.state, "app_config_repository", None)
    if repo is None or not hasattr(repo, "get_global_row"):
        raise HTTPException(
            status_code=501,
            detail="Limits administration requires Postgres app_limits",
        )
    return repo


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


# --- Resource limits (Postgres app_limits) ---


@router.get("/limits/global")
def get_limits_global_admin(
    request: Request,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    repo = _app_config_repo_or_501(request)
    row = repo.get_global_row()
    if not row:
        raise HTTPException(status_code=404, detail="Global limits row not found")
    logger.info("admin_get_limits_global | admin_user_id={}", ctx.user_id)
    return {"limits": _limits_row_snake(row)}


@router.put("/limits/global")
def put_limits_global_admin(
    request: Request,
    body: AppLimitsPayload,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    repo = _app_config_repo_or_501(request)
    limits = _app_limits_from_payload(body)
    repo.upsert_global_row(limits)
    logger.info("admin_put_limits_global | admin_user_id={}", ctx.user_id)
    return {"limits": _limits_row_snake(repo.get_global_row())}


@router.get("/limits/new-user-defaults")
def get_limits_new_user_defaults_admin(
    request: Request,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    repo = _app_config_repo_or_501(request)
    row = repo.get_new_user_defaults_row()
    if not row:
        raise HTTPException(status_code=404, detail="New-user defaults row not found")
    logger.info("admin_get_limits_new_user_defaults | admin_user_id={}", ctx.user_id)
    return {
        "limits": {
            "max_stages_per_job": row.get("max_stages_per_job"),
            "max_pipelines_per_stage": row.get("max_pipelines_per_stage"),
            "max_steps_per_pipeline": row.get("max_steps_per_pipeline"),
            "max_jobs_per_owner": row.get("max_jobs_per_owner"),
            "max_triggers_per_owner": row.get("max_triggers_per_owner"),
            "max_runs_per_utc_day": row.get("max_runs_per_utc_day"),
            "max_runs_per_utc_month": row.get("max_runs_per_utc_month"),
        }
    }


@router.put("/limits/new-user-defaults")
def put_limits_new_user_defaults_admin(
    request: Request,
    body: AppLimitsPayload,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    repo = _app_config_repo_or_501(request)
    limits = _app_limits_from_payload(body)
    repo.upsert_new_user_defaults(limits)
    logger.info("admin_put_limits_new_user_defaults | admin_user_id={}", ctx.user_id)
    row = repo.get_new_user_defaults_row()
    if not row:
        raise HTTPException(status_code=404, detail="New-user defaults row not found")
    return {
        "limits": {
            "max_stages_per_job": row.get("max_stages_per_job"),
            "max_pipelines_per_stage": row.get("max_pipelines_per_stage"),
            "max_steps_per_pipeline": row.get("max_steps_per_pipeline"),
            "max_jobs_per_owner": row.get("max_jobs_per_owner"),
            "max_triggers_per_owner": row.get("max_triggers_per_owner"),
            "max_runs_per_utc_day": row.get("max_runs_per_utc_day"),
            "max_runs_per_utc_month": row.get("max_runs_per_utc_month"),
        }
    }


@router.get("/limits/users/{user_id}")
def get_user_limits_detail_admin(
    request: Request,
    user_id: UUID,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    repo = _app_config_repo_or_501(request)
    uid = str(user_id)
    g = repo.get_global_row()
    u = repo.get_user_row(uid)
    if not g:
        raise HTTPException(status_code=404, detail="Global limits row not found")
    try:
        eff = resolve_effective_app_limits(g, u, owner_user_id=uid, operation="admin_user_detail")
    except LimitsResolutionError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    job_repo = getattr(request.app.state, "job_repository", None)
    trigger_repo = getattr(request.app.state, "trigger_repository", None)
    run_repo = getattr(request.app.state, "supabase_run_repository", None)
    n_jobs = len(job_repo.list_by_owner(uid)) if job_repo else 0
    n_triggers = len(trigger_repo.list_by_owner(uid)) if trigger_repo else 0

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    runs_day = 0
    runs_month = 0
    if run_repo is not None and hasattr(run_repo, "count_job_runs_owner_since_utc"):
        runs_day = run_repo.count_job_runs_owner_since_utc(uid, day_start.isoformat())
        runs_month = run_repo.count_job_runs_owner_since_utc(uid, month_start.isoformat())

    summary = limits_resolution_summary(g, u, eff)
    logger.info("admin_get_user_limits_detail | admin_user_id={} target_user_id={}", ctx.user_id, uid)
    return {
        "userId": uid,
        "global": _limits_row_snake(g),
        "userStored": _limits_row_snake(u),
        "effective": {
            "max_stages_per_job": eff.max_stages_per_job,
            "max_pipelines_per_stage": eff.max_pipelines_per_stage,
            "max_steps_per_pipeline": eff.max_steps_per_pipeline,
            "max_jobs_per_owner": eff.max_jobs_per_owner,
            "max_triggers_per_owner": eff.max_triggers_per_owner,
            "max_runs_per_utc_day": eff.max_runs_per_utc_day,
            "max_runs_per_utc_month": eff.max_runs_per_utc_month,
        },
        "resolution": {
            "hasUserStoredRow": summary["has_user_stored_row"],
            "effectiveMatchesGlobalEverywhere": summary["effective_matches_global_everywhere"],
            "dimensionsEffectiveBelowGlobal": summary["dimensions_effective_below_global"],
        },
        "usage": {
            "jobs": n_jobs,
            "triggers": n_triggers,
            "runsUtcDay": runs_day,
            "runsUtcMonth": runs_month,
        },
    }


@router.put("/limits/users/{user_id}")
def put_user_limits_admin(
    request: Request,
    user_id: UUID,
    body: AppLimitsPayload,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    repo = _app_config_repo_or_501(request)
    uid = str(user_id)
    limits = _app_limits_from_payload(body)
    repo.save(uid, limits)
    logger.info("admin_put_user_limits | admin_user_id={} target_user_id={}", ctx.user_id, uid)
    return get_user_limits_detail_admin(request, user_id, ctx)
