"""Management list endpoints for dashboard surfaces (p5_pr03). Owner-scoped, Bearer auth."""

import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from app.dependencies import AuthContext, require_managed_auth
from app.domain.errors import TriggerJobLinkPolicyError
from app.domain.runs import StepRun
from app.domain.triggers import TriggerDefinition
from app.repositories.yaml_loader import job_graph_to_yaml_dict, parse_job_graph
from app.services.pipeline_live_test.analyze import analyzer_payload_hash, analyze_live_test
from app.services.trigger_request_body import (
    build_trigger_payload,
    debug_payload_json_for_logging,
    default_keywords_request_body_schema,
    management_body_fields_to_schema,
    preview_string_for_log,
    validate_request_body_against_schema,
)
from app.services.validation_service import ValidationError

router = APIRouter(prefix="/management", tags=["management"])


def _normalize_trigger_path(path: str) -> str:
    """Ensure path has leading slash for trigger resolution."""
    p = (path or "").strip()
    return f"/{p}" if p and not p.startswith("/") else p or "/"


class TriggerBodyField(BaseModel):
    """One key in the HTTP POST JSON body clients must send when invoking the trigger."""

    name: str = Field(..., min_length=1, max_length=120)
    type: Literal["string", "number", "boolean"] = "string"
    required: bool = True
    max_length: int | None = Field(default=None, ge=1, le=10_000)


class CreateTriggerRequest(BaseModel):
    """Request body for POST /management/triggers."""

    path: str = Field(..., min_length=1, description="HTTP path for the trigger (e.g. /my-trigger)")
    display_name: str | None = Field(default=None, description="Optional display name")
    body_fields: list[TriggerBodyField] | None = Field(
        default=None,
        description="POST JSON body fields. Omit to default to a single required string field `keywords` (locations-compatible).",
    )


class PatchTriggerRequest(BaseModel):
    """Partial update for a trigger (e.g. body schema)."""

    display_name: str | None = None
    body_fields: list[TriggerBodyField] | None = Field(
        default=None,
        description="When set, replaces request_body_schema derived from these fields.",
    )


class CreatePipelineRequest(BaseModel):
    """Request body for POST /management/pipelines."""

    trigger_id: str = Field(..., min_length=1, description="ID of the trigger that starts this pipeline")
    target_id: str = Field(..., min_length=1, description="ID of the data target where output lands")
    display_name: str | None = Field(default=None, description="Optional display name")


class PatchPipelineStatusRequest(BaseModel):
    """Toggle whether a pipeline runs when its trigger fires (``active`` vs ``disabled``)."""

    status: Literal["active", "disabled"]


class LiveTestConfigBody(BaseModel):
    """Scope, fixtures, and API overrides for editor-initiated pipeline live tests."""

    scope_kind: Literal["job", "stage", "pipeline", "step"] = "job"
    stage_id: str | None = None
    pipeline_id: str | None = None
    step_id: str | None = None
    fixtures: dict[str, Any] | None = None
    api_overrides: dict[str, Any] | None = None
    allow_destination_writes: bool = False


class LiveTestAnalyzeRequest(BaseModel):
    """POST /management/pipelines/{id}/live-test/analyze body."""

    live_test: LiveTestConfigBody = Field(default_factory=LiveTestConfigBody)
    test_run_configuration_id: str | None = None


class LiveTestRunRequest(BaseModel):
    """POST /management/pipelines/{id}/run body."""

    trigger_body: dict[str, Any] = Field(
        ...,
        description="JSON fields matching the linked trigger's request_body_schema",
    )
    live_test: LiveTestConfigBody = Field(default_factory=LiveTestConfigBody)
    test_run_configuration_id: str | None = None


def _first_linked_trigger_id(link_repo, job_id: str, owner_user_id: str) -> str | None:
    ids = link_repo.list_trigger_ids_for_job(job_id, owner_user_id)
    return ids[0] if ids else None


def _merge_live_test_from_saved(
    job_repo,
    pipeline_id: str,
    owner_user_id: str,
    body: LiveTestConfigBody,
    test_run_configuration_id: str | None,
) -> dict[str, Any]:
    """Overlay request ``live_test`` on saved run configuration when id is provided."""
    overlay = body.model_dump(exclude_unset=True, exclude_none=True)
    if not test_run_configuration_id:
        return overlay
    graph = job_repo.get_graph_by_id(pipeline_id, owner_user_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    drs = graph.job.default_run_settings or {}
    live = drs.get("live_test") if isinstance(drs, dict) else {}
    if not isinstance(live, dict):
        live = {}
    configs = live.get("run_configurations") or []
    found = next(
        (
            c
            for c in configs
            if isinstance(c, dict) and c.get("id") == test_run_configuration_id
        ),
        None,
    )
    if not found:
        raise HTTPException(
            status_code=422,
            detail=f"test_run_configuration_id not found: {test_run_configuration_id!r}",
        )
    base = {k: v for k, v in found.items() if k not in ("id", "display_name")}
    merged = {**base, **overlay}
    return merged


def _serialize_datetime(dt):
    """Serialize datetime to ISO string or None."""
    if dt is None:
        return None
    return dt.isoformat()


def _step_trace_to_api(sr: StepRun) -> dict[str, Any]:
    """Map StepRun persistence to API shape (input / processing / output)."""
    return {
        "id": sr.id,
        "step_id": sr.step_id,
        "step_template_id": sr.step_template_id,
        "pipeline_id": sr.pipeline_id,
        "status": sr.status,
        "started_at": _serialize_datetime(sr.started_at),
        "completed_at": _serialize_datetime(sr.completed_at),
        "error_summary": sr.error_summary,
        "input": sr.input_summary,
        "processing": sr.processing_log or [],
        "output": sr.output_summary,
    }


def _apply_trigger_links_to_job_payload(
    payload: dict,
    job_id: str,
    owner_user_id: str,
    link_repo,
) -> dict:
    """Merge trigger_job_links into editor payload (``trigger_ids``, ``trigger_id``)."""
    if link_repo is None:
        return payload
    trigger_ids = link_repo.list_trigger_ids_for_job(job_id, owner_user_id)
    if len(trigger_ids) > 1:
        logger.warning(
            "management_pipeline_multiple_trigger_links | job_id={} owner={} trigger_ids={}",
            job_id,
            owner_user_id,
            trigger_ids,
        )
    out = dict(payload)
    out["trigger_ids"] = trigger_ids
    if trigger_ids:
        out["trigger_id"] = trigger_ids[0]
    else:
        out.pop("trigger_id", None)
    return out


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


@router.post("/bootstrap/reprovision-starter")
def reprovision_starter_job(
    request: Request,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    **Destructive:** remove the starter HTTP trigger at ``/locations`` and the job
    ``job_notion_place_inserter``, then re-import both from bundled YAML
    (``product_model/bootstrap/jobs/notion_place_inserter.yaml`` and the locations trigger).

    Use after editing bootstrap YAML so your account matches the repo. Generates a new trigger
    secret. Requires ``ENABLE_BOOTSTRAP_PROVISIONING`` (default on).
    """
    svc = getattr(request.app.state, "bootstrap_provisioning_service", None)
    if svc is None:
        raise HTTPException(
            status_code=503,
            detail="Bootstrap provisioning is disabled (ENABLE_BOOTSTRAP_PROVISIONING).",
        )
    if not hasattr(svc, "reprovision_owner_starter_definitions"):
        raise HTTPException(status_code=501, detail="Reprovision is not supported by this runtime.")
    try:
        svc.reprovision_owner_starter_definitions(ctx.user_id)
    except Exception as e:
        logger.exception("reprovision_starter_failed | owner={} error={}", ctx.user_id, e)
        raise HTTPException(status_code=500, detail="Reprovision failed") from e
    return {
        "status": "ok",
        "job_id": "job_notion_place_inserter",
        "trigger_path": "/locations",
        "message": (
            "Starter job and /locations trigger re-imported from bundled YAML. "
            "GET /management/triggers to see the new HTTP trigger secret."
        ),
    }


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
    link_repo = getattr(request.app.state, "trigger_job_link_repository", None)
    return _apply_trigger_links_to_job_payload(payload, pipeline_id, ctx.user_id, link_repo)


@router.patch("/pipelines/{pipeline_id}/status")
def patch_pipeline_status(
    request: Request,
    pipeline_id: str,
    body: PatchPipelineStatusRequest,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Set pipeline job status to ``active`` or ``disabled``.
    Disabled pipelines stay linked to triggers but are omitted from trigger dispatch.
    Archived pipelines are not accessible (404).
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
    # Status-only update: do not save_job_graph (that re-runs binding validation and can fail on valid multi-pipeline jobs).
    job_repo.update_job_status(pipeline_id, ctx.user_id, body.status)
    return {"id": pipeline_id, "status": body.status}


@router.post("/pipelines/{pipeline_id}/live-test/analyze")
def analyze_pipeline_live_test(
    request: Request,
    pipeline_id: str,
    body: LiveTestAnalyzeRequest,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Analyze a draft live-test configuration: fixture requirements, scoped destination-write
    policy, and planned external API call sites (with per-site override validation).
    """
    job_def_svc = getattr(request.app.state, "job_definition_service", None)
    link_repo = getattr(request.app.state, "trigger_job_link_repository", None)
    job_repo = getattr(request.app.state, "job_repository", None)
    if not job_def_svc or not link_repo or not job_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration"},
        )
    trigger_id = _first_linked_trigger_id(link_repo, pipeline_id, ctx.user_id)
    if not trigger_id:
        raise HTTPException(
            status_code=422,
            detail="Pipeline has no linked trigger; link a trigger before live testing",
        )
    snapshot_obj = job_def_svc.resolve_for_run(pipeline_id, ctx.user_id, trigger_id)
    if snapshot_obj is None:
        raise HTTPException(
            status_code=422,
            detail="Pipeline cannot be resolved (missing target, trigger, or archived)",
        )
    try:
        merged = _merge_live_test_from_saved(
            job_repo,
            pipeline_id,
            ctx.user_id,
            body.live_test,
            body.test_run_configuration_id,
        )
        scope_kind = str(merged.get("scope_kind", "job"))
        analysis = analyze_live_test(
            snapshot_obj.snapshot,
            scope_kind=scope_kind,
            stage_id=merged.get("stage_id"),
            pipeline_id=merged.get("pipeline_id"),
            step_id=merged.get("step_id"),
            fixtures=merged.get("fixtures"),
            api_overrides=merged.get("api_overrides"),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {
        **analysis,
        "analyzer_payload_hash": analyzer_payload_hash(analysis),
    }


@router.post("/pipelines/{pipeline_id}/run")
def enqueue_pipeline_live_test_run(
    request: Request,
    pipeline_id: str,
    body: LiveTestRunRequest,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Enqueue an editor-initiated pipeline run with live-test scope/fixtures/API overrides.
    Validates trigger body, runs the same analyzer as ``live-test/analyze``, then enqueues the worker.
    """
    job_def_svc = getattr(request.app.state, "job_definition_service", None)
    link_repo = getattr(request.app.state, "trigger_job_link_repository", None)
    job_repo = getattr(request.app.state, "job_repository", None)
    run_repo = getattr(request.app.state, "supabase_run_repository", None)
    queue_repo = getattr(request.app.state, "supabase_queue_repository", None)
    trigger_repo = getattr(request.app.state, "trigger_repository", None)
    if not all([job_def_svc, link_repo, job_repo, run_repo, queue_repo, trigger_repo]):
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration"},
        )

    trigger_id = _first_linked_trigger_id(link_repo, pipeline_id, ctx.user_id)
    if not trigger_id:
        raise HTTPException(
            status_code=422,
            detail="Pipeline has no linked trigger",
        )
    trigger = trigger_repo.get_by_id(trigger_id, ctx.user_id)
    if not trigger:
        raise HTTPException(status_code=422, detail="Linked trigger not found")

    try:
        merged = _merge_live_test_from_saved(
            job_repo,
            pipeline_id,
            ctx.user_id,
            body.live_test,
            body.test_run_configuration_id,
        )
    except HTTPException:
        raise
    schema = trigger.request_body_schema or default_keywords_request_body_schema()
    try:
        validated = validate_request_body_against_schema(body.trigger_body, schema)
        trigger_payload = build_trigger_payload(validated, schema)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    snapshot_obj = job_def_svc.resolve_for_run(pipeline_id, ctx.user_id, trigger_id)
    if snapshot_obj is None:
        raise HTTPException(
            status_code=422,
            detail="Pipeline cannot be resolved for run",
        )
    scope_kind = str(merged.get("scope_kind", "job"))
    analysis = analyze_live_test(
        snapshot_obj.snapshot,
        scope_kind=scope_kind,
        stage_id=merged.get("stage_id"),
        pipeline_id=merged.get("pipeline_id"),
        step_id=merged.get("step_id"),
        fixtures=merged.get("fixtures"),
        api_overrides=merged.get("api_overrides"),
    )
    if analysis.get("destination_write_blocked"):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Scoped run cannot include destination-writing steps",
                "destination_write_blocked": True,
                "unsatisfied_requirements": analysis.get("unsatisfied_requirements", []),
                "planned_external_calls": analysis.get("planned_external_calls", []),
            },
        )
    if not analysis.get("ok"):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Live test configuration is incomplete",
                "unsatisfied_requirements": analysis.get("unsatisfied_requirements", []),
                "planned_external_calls": analysis.get("planned_external_calls", []),
            },
        )

    ah = analyzer_payload_hash(analysis)
    meta = {
        "invocation_source": "editor_live_test",
        "scope_kind": scope_kind,
        "stage_id": merged.get("stage_id"),
        "pipeline_id": merged.get("pipeline_id"),
        "step_id": merged.get("step_id"),
        "allow_destination_writes": bool(merged.get("allow_destination_writes", False)),
        "analyzer_payload_hash": ah,
        "test_run_configuration_id": body.test_run_configuration_id,
    }
    trigger_payload = {
        **trigger_payload,
        "_live_test_meta": meta,
    }

    target_data = snapshot_obj.snapshot.get("target") or {}
    target_id = str(target_data.get("id", ""))

    job_id = f"loc_{uuid.uuid4().hex}"
    run_id = str(uuid.uuid4())

    log_preview = preview_string_for_log(
        {k: v for k, v in trigger_payload.items() if k != "_live_test_meta"}
    )

    live_test_queue = {
        "invocation_source": "editor_live_test",
        "scope_kind": scope_kind,
        "stage_id": merged.get("stage_id"),
        "pipeline_id": merged.get("pipeline_id"),
        "step_id": merged.get("step_id"),
        "fixtures": merged.get("fixtures") or {},
        "api_overrides": merged.get("api_overrides") or {},
        "allow_destination_writes": bool(merged.get("allow_destination_writes", False)),
    }

    try:
        run_repo.create_job(
            job_id=job_id,
            trigger_payload=trigger_payload,
            status="queued",
            owner_user_id=ctx.user_id,
            run_id=run_id,
            job_definition_id=pipeline_id,
            trigger_id=trigger_id,
            target_id=target_id,
            definition_snapshot_ref=snapshot_obj.snapshot_ref,
        )
        live_test_queue_payload = {
            "job_id": job_id,
            "run_id": run_id,
            "trigger_payload": trigger_payload,
            "live_test": live_test_queue,
            "job_definition_id": pipeline_id,
            "trigger_id": trigger_id,
            "job_slug": "notion_place_inserter",
            "definition_snapshot_ref": snapshot_obj.snapshot_ref,
            "owner_user_id": ctx.user_id,
            "keywords": log_preview,
        }
        send_result = queue_repo.send(live_test_queue_payload, delay_seconds=0)
        logger.debug(
            "management_live_test_enqueue_payload_json | run_id={} pipeline_id={} payload_json={}",
            run_id,
            pipeline_id,
            debug_payload_json_for_logging(live_test_queue_payload),
        )
    except Exception:
        logger.exception(
            "management_live_test_enqueue_failed | pipeline_id={} run_id={}",
            pipeline_id,
            run_id,
        )
        raise HTTPException(status_code=503, detail="Unable to enqueue run")

    logger.info(
        "management_live_test_enqueued | pipeline_id={} run_id={} job_id={} scope_kind={} "
        "pgmq_message_id={} queue_name={}",
        pipeline_id,
        run_id,
        job_id,
        scope_kind,
        send_result.message_id,
        queue_repo._config.queue_name,
    )
    return {"status": "accepted", "run_id": run_id, "job_id": job_id}


@router.get("/runs/{run_id}")
def get_management_run(
    request: Request,
    run_id: str,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """Poll job run status for management UI (e.g. pipeline editor live test)."""
    run_repo = getattr(request.app.state, "supabase_run_repository", None)
    if not run_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: run repository not available"},
        )
    row = run_repo.get_job_run(run_id, ctx.user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    step_traces: list[dict[str, Any]] = []
    list_fn = getattr(run_repo, "list_step_runs_for_job_run", None)
    if list_fn is not None:
        try:
            raw = list_fn(row.id, ctx.user_id)
            if isinstance(raw, list):
                step_traces = [
                    _step_trace_to_api(sr) for sr in raw if isinstance(sr, StepRun)
                ]
        except Exception:
            logger.exception(
                "management_get_run_step_traces_failed | run_id={}",
                run_id,
            )
    return {
        "id": row.id,
        "status": row.status,
        "error_summary": row.error_summary,
        "job_id": row.job_id,
        "trigger_id": row.trigger_id,
        "target_id": row.target_id,
        "platform_job_id": row.platform_job_id,
        "definition_snapshot_ref": row.definition_snapshot_ref,
        "retry_count": row.retry_count,
        "started_at": _serialize_datetime(row.started_at),
        "completed_at": _serialize_datetime(row.completed_at),
        "trigger_payload": row.trigger_payload,
        "result_json": row.result_json,
        "step_traces": step_traces,
    }


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
    link_repo = getattr(request.app.state, "trigger_job_link_repository", None)
    saved = job_repo.get_graph_by_id(pipeline_id, ctx.user_id)
    payload = job_graph_to_yaml_dict(saved) if saved else {"id": pipeline_id}
    return _apply_trigger_links_to_job_payload(payload, pipeline_id, ctx.user_id, link_repo)


@router.post("/pipelines")
def create_pipeline(
    request: Request,
    body: CreatePipelineRequest,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Create a new pipeline. Requires trigger_id and target_id.
    Links the trigger to the job and returns full graph payload for editor load.
    """
    job_repo = getattr(request.app.state, "job_repository", None)
    if not job_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: job repository not available"},
        )
    target_repo = getattr(request.app.state, "target_repository", None)
    if not target_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: target repository not available"},
        )
    trigger_repo = getattr(request.app.state, "trigger_repository", None)
    if not trigger_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: trigger repository not available"},
        )
    link_repo = getattr(request.app.state, "trigger_job_link_repository", None)
    if not link_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: trigger job link repository not available"},
        )

    trigger_id = (body.trigger_id or "").strip()
    target_id = (body.target_id or "").strip()
    display_name = (body.display_name or "").strip() or "New Pipeline"

    if not trigger_id:
        return JSONResponse(
            status_code=422,
            content={"detail": "trigger_id is required", "code": "NO_TRIGGER"},
        )
    if not target_id or target_id == "placeholder":
        return JSONResponse(
            status_code=422,
            content={
                "detail": "target_id is required. Create a target first by connecting a Notion database in Database Targets.",
                "code": "NO_TARGET",
            },
        )

    trigger = trigger_repo.get_by_id(trigger_id, ctx.user_id)
    if not trigger:
        return JSONResponse(
            status_code=422,
            content={"detail": "Trigger not found or not owned by you", "code": "INVALID_TRIGGER"},
        )
    target = target_repo.get_by_id(target_id, ctx.user_id)
    if not target:
        return JSONResponse(
            status_code=422,
            content={"detail": "Data target not found or not owned by you", "code": "INVALID_TARGET"},
        )

    job_id = f"job_{uuid.uuid4().hex[:12]}"
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
    try:
        link_repo.attach(trigger_id, job_id, ctx.user_id)
    except TriggerJobLinkPolicyError as e:
        return JSONResponse(
            status_code=422,
            content={"detail": e.message, "code": e.code},
        )
    saved = job_repo.get_graph_by_id(job_id, ctx.user_id)
    payload = job_graph_to_yaml_dict(saved) if saved else {"id": job_id}
    return _apply_trigger_links_to_job_payload(payload, job_id, ctx.user_id, link_repo)


@router.delete("/pipelines/{pipeline_id}")
def delete_pipeline(
    request: Request,
    pipeline_id: str,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Archive a pipeline (soft-delete). Sets status to archived.
    Archived pipelines are excluded from list and get; they no longer execute.
    """
    job_repo = getattr(request.app.state, "job_repository", None)
    if not job_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: job repository not available"},
        )
    # Verify pipeline exists and is owned before archiving
    graph = job_repo.get_graph_by_id(pipeline_id, ctx.user_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    job_repo.archive(pipeline_id, ctx.user_id)
    return {"status": "archived", "id": pipeline_id}


@router.get("/data-targets")
def list_data_targets(
    request: Request,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    List data targets for the authenticated owner.
    Returns id, display_name, target_template_id, connector_instance_id,
    external_target_id, status, active_schema_snapshot_id.
    """
    target_repo = getattr(request.app.state, "target_repository", None)
    if not target_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: target repository not available"},
        )
    targets = target_repo.list_by_owner(ctx.user_id)
    # Deduplicate by (connector_instance_id, external_target_id): same Notion DB can appear
    # as both a bootstrap target (target_places_to_visit, target_locations) and a
    # per-source target (target_notion_*). Prefer bootstrap IDs for consistency with jobs.
    bootstrap_ids = {"target_places_to_visit", "target_locations"}
    seen: dict[tuple[str, str], dict] = {}
    for t in targets:
        key = (t.connector_instance_id or "", t.external_target_id or "")
        item = {
            "id": t.id,
            "display_name": t.display_name,
            "target_template_id": t.target_template_id,
            "connector_instance_id": t.connector_instance_id,
            "external_target_id": t.external_target_id,
            "status": t.status,
            "active_schema_snapshot_id": t.active_schema_snapshot_id,
        }
        if key not in seen or t.id in bootstrap_ids:
            seen[key] = item
        elif seen[key]["id"] not in bootstrap_ids and t.id in bootstrap_ids:
            seen[key] = item
    items = list(seen.values())
    return {"items": items}


@router.get("/data-targets/{target_id}/schema")
def get_data_target_schema(
    request: Request,
    target_id: str,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Fetch active schema for a data target. Owner-scoped.
    Returns target summary plus properties with name, type, id, select/multi_select options.
    """
    target_repo = getattr(request.app.state, "target_repository", None)
    if not target_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: target repository not available"},
        )
    target_schema_repo = getattr(request.app.state, "target_schema_repository", None)
    if not target_schema_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: target schema repository not available"},
        )
    target = target_repo.get_by_id(target_id, ctx.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Data target not found")
    schema = None
    if target.active_schema_snapshot_id:
        schema = target_schema_repo.get_by_id(target.active_schema_snapshot_id, ctx.user_id)
    if not schema:
        schema = target_schema_repo.get_active_for_target(target_id, ctx.user_id)
    properties = []
    if schema:
        for p in schema.properties:
            prop = {
                "id": p.id,
                "external_property_id": p.external_property_id,
                "name": p.name,
                "normalized_slug": p.normalized_slug,
                "property_type": p.property_type,
                "required": p.required,
                "readonly": p.readonly,
            }
            if p.options:
                prop["options"] = p.options
            if p.metadata:
                prop["metadata"] = p.metadata
            properties.append(prop)
    return {
        "target_id": target_id,
        "display_name": target.display_name,
        "connector_instance_id": target.connector_instance_id,
        "external_target_id": target.external_target_id,
        "last_synced_at": _serialize_datetime(schema.fetched_at) if schema else None,
        "schema_snapshot_id": schema.id if schema else None,
        "properties": properties,
    }


@router.get("/step-templates")
def list_step_templates(
    request: Request,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    List step templates for the pipeline editor picker.
    Returns id, display_name, category, status, description, input_contract,
    output_contract, config_schema for schema-driven inspector forms.
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
            "slug": t.slug,
            "display_name": t.display_name,
            "step_kind": t.step_kind,
            "category": t.category,
            "status": t.status,
            "description": t.description or "",
            "input_contract": t.input_contract or {},
            "output_contract": t.output_contract or {},
            "config_schema": t.config_schema or {},
            "runtime_binding": t.runtime_binding or "",
        }
        for t in templates
    ]
    return {"items": items}


@router.get("/step-templates/{template_id}")
def get_step_template(
    request: Request,
    template_id: str,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Fetch full step template metadata for the inspector.
    Returns input_contract, output_contract, config_schema for schema-driven forms.
    """
    step_template_repo = getattr(request.app.state, "step_template_repository", None)
    if not step_template_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: step template repository not available"},
        )
    template = step_template_repo.get_by_id(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Step template not found")
    return {
        "id": template.id,
        "slug": template.slug,
        "display_name": template.display_name,
        "step_kind": template.step_kind,
        "description": template.description or "",
        "input_contract": template.input_contract or {},
        "output_contract": template.output_contract or {},
        "config_schema": template.config_schema or {},
        "runtime_binding": template.runtime_binding or "",
        "category": template.category or "general",
        "status": template.status,
    }


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
            "request_body_schema": t.request_body_schema,
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
    Optional ``body_fields`` defines the JSON POST body shape (default: required string ``keywords``).
    Returns created trigger with secret (shown once; copy and store).
    """
    client_host = request.client.host if request.client else None
    body_fields_count = len(body.body_fields) if body.body_fields else 0
    logger.info(
        "management_create_trigger_start | user_id={} client_host={} path_raw={!r} "
        "display_name_in={!r} body_fields_count={}",
        ctx.user_id,
        client_host,
        body.path,
        body.display_name,
        body_fields_count,
    )
    if body.body_fields:
        logger.info(
            "management_create_trigger_body_fields | user_id={} fields={}",
            ctx.user_id,
            [(f.name, f.type, f.required, f.max_length) for f in body.body_fields],
        )

    trigger_repo = getattr(request.app.state, "trigger_repository", None)
    if not trigger_repo:
        logger.error("management_create_trigger_no_repo | user_id={}", ctx.user_id)
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: trigger repository not available",
        )
    normalized_path = _normalize_trigger_path(body.path)
    logger.info(
        "management_create_trigger_path_normalized | user_id={} path_raw={!r} path={!r}",
        ctx.user_id,
        body.path,
        normalized_path,
    )
    existing = trigger_repo.get_by_path(normalized_path, ctx.user_id)
    if existing is not None:
        logger.warning(
            "management_create_trigger_conflict | user_id={} path={!r} existing_trigger_id={}",
            ctx.user_id,
            normalized_path,
            existing.id,
        )
        raise HTTPException(
            status_code=409,
            detail=f"Trigger path '{normalized_path}' already in use for this account",
        )
    try:
        if body.body_fields:
            schema = management_body_fields_to_schema(
                [f.model_dump() for f in body.body_fields]
            )
            logger.info(
                "management_create_trigger_schema_mode | user_id={} mode=custom_body_fields",
                ctx.user_id,
            )
        else:
            schema = default_keywords_request_body_schema()
            logger.info(
                "management_create_trigger_schema_mode | user_id={} mode=default_keywords",
                ctx.user_id,
            )
    except ValueError as e:
        logger.warning(
            "management_create_trigger_schema_invalid | user_id={} error={!s}",
            ctx.user_id,
            e,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e

    logger.debug(
        "management_create_trigger_request_body_schema | user_id={} schema={}",
        ctx.user_id,
        schema,
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
        request_body_schema=schema,
        status="active",
        auth_mode="bearer",
        secret_value=secret_value,
        secret_last_rotated_at=now,
        visibility="owner",
        created_at=now,
        updated_at=now,
    )
    trigger_repo.save(trigger)
    schema_summary = (
        list(schema.keys())
        if isinstance(schema, dict)
        else type(schema).__name__
    )
    logger.info(
        "management_create_trigger_ok | trigger_id={} user_id={} path={!r} display_name={!r} "
        "request_body_schema_top_keys={} secret_len_chars={} (secret value not logged)",
        trigger_id,
        ctx.user_id,
        normalized_path,
        display_name,
        schema_summary,
        len(secret_value),
    )
    return {
        "id": trigger.id,
        "display_name": trigger.display_name,
        "trigger_type": trigger.trigger_type,
        "path": trigger.path,
        "method": trigger.method,
        "status": trigger.status,
        "auth_mode": trigger.auth_mode,
        "request_body_schema": trigger.request_body_schema,
        "secret": secret_value,
        "secret_last_rotated_at": _serialize_datetime(trigger.secret_last_rotated_at),
        "updated_at": _serialize_datetime(trigger.updated_at),
    }


@router.patch("/triggers/{trigger_id}")
def patch_trigger(
    request: Request,
    trigger_id: str,
    body: PatchTriggerRequest,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """Update trigger metadata and/or POST body schema (from ``body_fields``)."""
    trigger_repo = getattr(request.app.state, "trigger_repository", None)
    if not trigger_repo:
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: trigger repository not available",
        )
    trigger = trigger_repo.get_by_id(trigger_id, ctx.user_id)
    if trigger is None:
        raise HTTPException(status_code=404, detail="Trigger not found")
    now = datetime.now(timezone.utc)
    if body.display_name is not None:
        d = body.display_name.strip()
        if d:
            trigger.display_name = d
    if body.body_fields is not None:
        try:
            trigger.request_body_schema = management_body_fields_to_schema(
                [f.model_dump() for f in body.body_fields]
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    trigger.updated_at = now
    trigger_repo.save(trigger)
    return {
        "id": trigger.id,
        "display_name": trigger.display_name,
        "trigger_type": trigger.trigger_type,
        "path": trigger.path,
        "method": trigger.method,
        "status": trigger.status,
        "auth_mode": trigger.auth_mode,
        "request_body_schema": trigger.request_body_schema,
        "secret": trigger.secret_value,
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
