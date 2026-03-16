"""Management list endpoints for dashboard surfaces (p5_pr03). Owner-scoped, Bearer auth."""

import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.dependencies import AuthContext, require_managed_auth
from app.domain.triggers import TriggerDefinition
from app.repositories.yaml_loader import job_graph_to_yaml_dict, parse_job_graph
from app.services.validation_service import ValidationError

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


@router.get("/pipelines/{pipeline_id}")
def get_pipeline(
    request: Request,
    pipeline_id: str,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Fetch full job graph for editing. Returns editable payload (kind, id, display_name,
    target_id, stages with nested pipelines and steps).
    """
    job_repo = getattr(request.app.state, "job_repository", None)
    if not job_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: job repository not available"},
        )
    graph = job_repo.get_graph_by_id(pipeline_id, ctx.user_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    payload = job_graph_to_yaml_dict(graph)
    return payload


@router.put("/pipelines/{pipeline_id}")
def save_pipeline(
    request: Request,
    pipeline_id: str,
    body: dict = Body(...),
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Persist job graph. Accepts full editable payload. Creates or updates.
    Returns 422 with validation_errors when validation fails.
    """
    job_repo = getattr(request.app.state, "job_repository", None)
    if not job_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: job repository not available"},
        )
    try:
        graph = parse_job_graph(body, owner_user_id_override=ctx.user_id)
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid payload: {e!s}",
        )
    # Enforce path id and owner for security
    graph.job.id = pipeline_id
    graph.job.owner_user_id = ctx.user_id
    for stage in graph.stages:
        stage.job_id = pipeline_id
        stage.owner_user_id = ctx.user_id
    for pipeline in graph.pipelines:
        pipeline.owner_user_id = ctx.user_id
    for step in graph.steps:
        step.owner_user_id = ctx.user_id
    try:
        job_repo.save_job_graph(graph, skip_reference_checks=True)
    except ValidationError as e:
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation failed", "validation_errors": e.errors},
        )
    # Return canonical saved payload
    saved = job_repo.get_graph_by_id(pipeline_id, ctx.user_id)
    return job_graph_to_yaml_dict(saved) if saved else {"id": pipeline_id}


@router.post("/pipelines")
def create_pipeline(
    request: Request,
    body: dict = Body(default_factory=dict),
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Create a new pipeline. Accepts minimal payload (display_name, target_id optional).
    Returns full graph payload with generated id for editor load.
    """
    job_repo = getattr(request.app.state, "job_repository", None)
    if not job_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: job repository not available"},
        )
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    display_name = (body.get("display_name") or "").strip() or "New Pipeline"
    target_id = (body.get("target_id") or "").strip() or "placeholder"
    # Build minimal valid graph: job + 1 stage + 1 pipeline + 1 property_set step
    from app.domain.jobs import JobDefinition, PipelineDefinition, StageDefinition, StepInstance

    stage_id = f"stage_{uuid.uuid4().hex[:8]}"
    pipeline_id = f"pipeline_{uuid.uuid4().hex[:8]}"
    step_id = f"step_{uuid.uuid4().hex[:8]}"
    job = JobDefinition(
        id=job_id,
        owner_user_id=ctx.user_id,
        display_name=display_name,
        target_id=target_id,
        status="active",
        stage_ids=[stage_id],
    )
    stage = StageDefinition(
        id=stage_id,
        job_id=job_id,
        display_name="Stage 1",
        sequence=1,
        pipeline_ids=[pipeline_id],
        pipeline_run_mode="parallel",
    )
    pipeline = PipelineDefinition(
        id=pipeline_id,
        stage_id=stage_id,
        display_name="Pipeline 1",
        sequence=1,
        step_ids=[step_id],
    )
    step = StepInstance(
        id=step_id,
        pipeline_id=pipeline_id,
        step_template_id="step_template_property_set",
        display_name="Property Set",
        sequence=1,
        input_bindings={},
        config={
            "data_target_id": target_id,
            "target_kind": "page_metadata",
            "target_field": "cover_image",
        },
    )
    from app.services.validation_service import JobGraph

    graph = JobGraph(job=job, stages=[stage], pipelines=[pipeline], steps=[step])
    try:
        job_repo.save_job_graph(graph, skip_reference_checks=True)
    except ValidationError as e:
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation failed", "validation_errors": e.errors},
        )
    saved = job_repo.get_graph_by_id(job_id, ctx.user_id)
    return job_graph_to_yaml_dict(saved) if saved else {"id": job_id}


@router.get("/step-templates")
def list_step_templates(
    request: Request,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    List step templates for the pipeline editor picker.
    Returns id, display_name, category, status, description.
    """
    step_template_repo = getattr(request.app.state, "step_template_repository", None)
    if not step_template_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: step template repository not available"},
        )
    templates = step_template_repo.list_all()
    items = [
        {
            "id": t.id,
            "display_name": t.display_name,
            "category": t.category,
            "status": t.status,
            "description": t.description or "",
        }
        for t in templates
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
