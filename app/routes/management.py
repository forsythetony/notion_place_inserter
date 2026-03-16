"""Management list endpoints for dashboard surfaces (p5_pr03). Owner-scoped, Bearer auth."""

import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.dependencies import AuthContext, require_managed_auth
from app.domain.triggers import TriggerDefinition

router = APIRouter(prefix="/management", tags=["management"])


def _normalize_trigger_path(path: str) -> str:
    """Ensure path has leading slash for trigger resolution."""
    p = (path or "").strip()
    return f"/{p}" if p and not p.startswith("/") else p or "/"


class CreateTriggerRequest(BaseModel):
    """Request body for POST /management/triggers."""

    path: str = Field(..., min_length=1, description="HTTP path for the trigger (e.g. /my-trigger)")
    display_name: str | None = Field(default=None, description="Optional display name")


def _serialize_datetime(dt):
    """Serialize datetime to ISO string or None."""
    if dt is None:
        return None
    return dt.isoformat()


@router.get("/pipelines")
def list_pipelines(
    request: Request,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    List job definitions for the authenticated owner.
    Returns id, display_name, status, updated_at.
    """
    job_repo = getattr(request.app.state, "job_repository", None)
    if not job_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: job repository not available"},
        )
    jobs = job_repo.list_by_owner(ctx.user_id)
    items = [
        {
            "id": j.id,
            "display_name": j.display_name,
            "status": j.status,
            "updated_at": _serialize_datetime(j.updated_at),
        }
        for j in jobs
    ]
    return {"items": items}


@router.get("/connections")
def list_connections(
    request: Request,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    List connector instances for the authenticated owner.
    Returns id, display_name, status, connector_template_id, last_validated_at, last_error.
    """
    conn_repo = getattr(request.app.state, "connector_instance_repository", None)
    if not conn_repo:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Server misconfiguration: connector instance repository not available"
            },
        )
    instances = conn_repo.list_by_owner(ctx.user_id)
    items = [
        {
            "id": c.id,
            "display_name": c.display_name,
            "status": c.status,
            "connector_template_id": c.connector_template_id,
            "last_validated_at": _serialize_datetime(c.last_validated_at),
            "last_error": c.last_error,
            "auth_status": getattr(c, "auth_status", "pending"),
            "provider_account_name": getattr(c, "provider_account_name", None),
        }
        for c in instances
    ]
    return {"items": items}


@router.get("/triggers")
def list_triggers(
    request: Request,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    List trigger definitions for the authenticated owner.
    Returns id, display_name, trigger_type, path, method, status, auth_mode,
    secret, secret_last_rotated_at, updated_at.
    Trigger-job linkage is many-to-many via trigger_job_links; use link API for associations.
    """
    trigger_repo = getattr(request.app.state, "trigger_repository", None)
    if not trigger_repo:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Server misconfiguration: trigger repository not available"
            },
        )
    triggers = trigger_repo.list_by_owner(ctx.user_id)
    items = [
        {
            "id": t.id,
            "display_name": t.display_name,
            "trigger_type": t.trigger_type,
            "path": t.path,
            "method": t.method,
            "status": t.status,
            "auth_mode": t.auth_mode,
            "secret": t.secret_value,
            "secret_last_rotated_at": _serialize_datetime(t.secret_last_rotated_at),
            "updated_at": _serialize_datetime(t.updated_at),
        }
        for t in triggers
    ]
    return {"items": items}


@router.post("/triggers")
def create_trigger(
    request: Request,
    body: CreateTriggerRequest,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Create a new HTTP trigger. Path and optional display_name required.
    Fixed: method POST, body { keywords: string }. Trigger is unlinked until assigned to a pipeline.
    Returns created trigger with secret (shown once; copy and store).
    """
    trigger_repo = getattr(request.app.state, "trigger_repository", None)
    if not trigger_repo:
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: trigger repository not available",
        )
    normalized_path = _normalize_trigger_path(body.path)
    existing = trigger_repo.get_by_path(normalized_path, ctx.user_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Trigger path '{normalized_path}' already in use for this account",
        )
    trigger_id = f"trigger_{uuid.uuid4().hex[:12]}"
    secret_value = secrets.token_hex(15)
    now = datetime.now(timezone.utc)
    display_name = (body.display_name or "").strip() or normalized_path
    trigger = TriggerDefinition(
        id=trigger_id,
        owner_user_id=ctx.user_id,
        trigger_type="http",
        display_name=display_name,
        path=normalized_path,
        method="POST",
        request_body_schema={"keywords": "string"},
        status="active",
        auth_mode="bearer",
        secret_value=secret_value,
        secret_last_rotated_at=now,
        visibility="owner",
        created_at=now,
        updated_at=now,
    )
    trigger_repo.save(trigger)
    return {
        "id": trigger.id,
        "display_name": trigger.display_name,
        "trigger_type": trigger.trigger_type,
        "path": trigger.path,
        "method": trigger.method,
        "status": trigger.status,
        "auth_mode": trigger.auth_mode,
        "secret": secret_value,
        "secret_last_rotated_at": _serialize_datetime(trigger.secret_last_rotated_at),
        "updated_at": _serialize_datetime(trigger.updated_at),
    }


@router.post("/triggers/{trigger_id}/rotate-secret")
def rotate_trigger_secret(
    request: Request,
    trigger_id: str,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Rotate the trigger's HTTP secret. Returns the new secret in the response.
    Caller must store it; it is not shown again. Users cannot set secrets; only rotate.
    """
    trigger_repo = getattr(request.app.state, "trigger_repository", None)
    if not trigger_repo:
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: trigger repository not available",
        )
    if not hasattr(trigger_repo, "rotate_secret"):
        raise HTTPException(
            status_code=501,
            detail="Secret rotation not available for this trigger backend",
        )
    try:
        updated, new_secret = trigger_repo.rotate_secret(trigger_id, ctx.user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "id": updated.id,
        "secret": new_secret,
        "secret_last_rotated_at": _serialize_datetime(updated.secret_last_rotated_at),
    }


@router.get("/account")
def get_account(
    request: Request,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Return account context for the authenticated user: user_id, email, user_type,
    plus app limits when available.
    """
    auth_repo = getattr(request.app.state, "supabase_auth_repository", None)
    if not auth_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: auth repository not available"},
        )
    profile = auth_repo.get_profile(ctx.user_id)
    if not profile:
        return JSONResponse(status_code=403, content={"detail": "Profile not found"})
    user_type = profile.get("user_type")
    if not user_type:
        return JSONResponse(
            status_code=403, content={"detail": "Profile incomplete"}
        )

    payload = {
        "user_id": ctx.user_id,
        "email": ctx.email,
        "user_type": user_type,
    }

    app_config_repo = getattr(request.app.state, "app_config_repository", None)
    if app_config_repo:
        limits = app_config_repo.get_by_owner(ctx.user_id)
        if limits:
            payload["limits"] = {
                "max_stages_per_job": limits.max_stages_per_job,
                "max_pipelines_per_stage": limits.max_pipelines_per_stage,
                "max_steps_per_pipeline": limits.max_steps_per_pipeline,
            }

    return payload
