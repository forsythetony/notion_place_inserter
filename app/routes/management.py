"""Management list endpoints for dashboard surfaces (p5_pr03). Owner-scoped, Bearer auth."""

import asyncio
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
from loguru import logger
from pydantic import BaseModel, Field

from app.dependencies import AuthContext, require_managed_auth
from app.domain.errors import TriggerJobLinkPolicyError
from app.repositories.postgres_repositories import PostgresTriggerJobLinkRepository
from app.domain.runs import StepRun
from app.domain.triggers import TriggerDefinition
from app.repositories.yaml_loader import job_graph_to_yaml_dict, load_yaml_file, parse_job_graph
from app.services.job_graph_id_clone import clone_job_graph_with_prefixed_ids
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


async def _first_linked_trigger_id(
    link_repo, job_id: str, owner_user_id: str
) -> str | None:
    ids = await link_repo.list_trigger_ids_for_job(job_id, owner_user_id)
    return ids[0] if ids else None


async def _merge_live_test_from_saved(
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
    graph = await job_repo.get_graph_by_id(pipeline_id, owner_user_id)
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


async def _apply_trigger_links_to_job_payload(
    payload: dict,
    job_id: str,
    owner_user_id: str,
    link_repo,
) -> dict:
    """Merge trigger_job_links into editor payload (``trigger_ids``, ``trigger_id``)."""
    if link_repo is None:
        return payload
    trigger_ids = await link_repo.list_trigger_ids_for_job(job_id, owner_user_id)
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
async def list_pipelines(
    request: Request,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    List job definitions for the authenticated owner.
    Returns id, display_name, status, updated_at, trigger_name (linked trigger id, if any),
    and trigger_display_name (TriggerDefinition.display_name) when the trigger row exists.
    """
    job_repo = getattr(request.app.state, "job_repository", None)
    if not job_repo:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server misconfiguration: job repository not available"},
        )
    jobs = await job_repo.list_by_owner(ctx.user_id)
    link_repo = getattr(request.app.state, "trigger_job_link_repository", None)
    if link_repo and isinstance(link_repo, PostgresTriggerJobLinkRepository):
        job_ids = [j.id for j in jobs]
        link_map = await link_repo.map_trigger_ids_for_jobs(ctx.user_id, job_ids)
    elif link_repo:
        link_lists = await asyncio.gather(
            *[link_repo.list_trigger_ids_for_job(j.id, ctx.user_id) for j in jobs]
        )
        link_map = {j.id: tids for j, tids in zip(jobs, link_lists)}
    else:
        link_map = {}

    trigger_repo = getattr(request.app.state, "trigger_repository", None)
    job_rows = []
    for j in jobs:
        tids = link_map.get(j.id) or []
        tid = tids[0] if tids else None
        job_rows.append((j, tid))

    unique_trigger_ids = sorted({tid for _, tid in job_rows if tid})
    id_to_display: dict[str, str] = {}
    if trigger_repo and unique_trigger_ids:
        fetched = await asyncio.gather(
            *[trigger_repo.get_by_id(tid, ctx.user_id) for tid in unique_trigger_ids]
        )
        for tid, tr in zip(unique_trigger_ids, fetched):
            if tr is not None and (tr.display_name or "").strip():
                id_to_display[tid] = tr.display_name.strip()

    items = []
    for j, tid in job_rows:
        items.append(
            {
                "id": j.id,
                "display_name": j.display_name,
                "status": j.status,
                "updated_at": _serialize_datetime(j.updated_at),
                "trigger_name": tid,
                "trigger_display_name": id_to_display.get(tid) if tid else None,
            }
        )
    return {"items": items}


@router.post("/bootstrap/reprovision-starter")
async def reprovision_starter_job(
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
        await svc.reprovision_owner_starter_definitions(ctx.user_id)
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
async def get_pipeline(
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
    graph = await job_repo.get_graph_by_id(pipeline_id, ctx.user_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    payload = job_graph_to_yaml_dict(graph)
    link_repo = getattr(request.app.state, "trigger_job_link_repository", None)
    return await _apply_trigger_links_to_job_payload(
        payload, pipeline_id, ctx.user_id, link_repo
    )


@router.patch("/pipelines/{pipeline_id}/status")
async def patch_pipeline_status(
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
    graph = await job_repo.get_graph_by_id(pipeline_id, ctx.user_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    # Status-only update: do not save_job_graph (that re-runs binding validation and can fail on valid multi-pipeline jobs).
    await job_repo.update_job_status(pipeline_id, ctx.user_id, body.status)
    return {"id": pipeline_id, "status": body.status}


@router.post("/pipelines/{pipeline_id}/live-test/analyze")
async def analyze_pipeline_live_test(
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
    trigger_id = await _first_linked_trigger_id(link_repo, pipeline_id, ctx.user_id)
    if not trigger_id:
        raise HTTPException(
            status_code=422,
            detail="Pipeline has no linked trigger; link a trigger before live testing",
        )
    snapshot_obj = await job_def_svc.resolve_for_run(pipeline_id, ctx.user_id, trigger_id)
    if snapshot_obj is None:
        raise HTTPException(
            status_code=422,
            detail="Pipeline cannot be resolved (missing target, trigger, or archived)",
        )
    try:
        merged = await _merge_live_test_from_saved(
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
async def enqueue_pipeline_live_test_run(
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

    trigger_id = await _first_linked_trigger_id(link_repo, pipeline_id, ctx.user_id)
    if not trigger_id:
        raise HTTPException(
            status_code=422,
            detail="Pipeline has no linked trigger",
        )
    trigger = await trigger_repo.get_by_id(trigger_id, ctx.user_id)
    if not trigger:
        raise HTTPException(status_code=422, detail="Linked trigger not found")

    try:
        merged = await _merge_live_test_from_saved(
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

    snapshot_obj = await job_def_svc.resolve_for_run(pipeline_id, ctx.user_id, trigger_id)
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
        await run_repo.create_job(
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
        send_result = await queue_repo.send(live_test_queue_payload, delay_seconds=0)
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
async def get_management_run(
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
    row = await run_repo.get_job_run(run_id, ctx.user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    step_traces: list[dict[str, Any]] = []
    list_fn = getattr(run_repo, "list_step_runs_for_job_run", None)
    if list_fn is not None:
        try:
            raw = await list_fn(row.id, ctx.user_id)
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
async def save_pipeline(
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
        await job_repo.save_job_graph(graph, skip_reference_checks=True)
    except ValidationError as e:
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation failed", "validation_errors": e.errors},
        )
    link_repo = getattr(request.app.state, "trigger_job_link_repository", None)
    saved = await job_repo.get_graph_by_id(pipeline_id, ctx.user_id)
    payload = job_graph_to_yaml_dict(saved) if saved else {"id": pipeline_id}
    return await _apply_trigger_links_to_job_payload(
        payload, pipeline_id, ctx.user_id, link_repo
    )


@router.post("/pipelines")
async def create_pipeline(
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

    trigger = await trigger_repo.get_by_id(trigger_id, ctx.user_id)
    if not trigger:
        return JSONResponse(
            status_code=422,
            content={"detail": "Trigger not found or not owned by you", "code": "INVALID_TRIGGER"},
        )
    target = await target_repo.get_by_id(target_id, ctx.user_id)
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
    app_config_repo = getattr(request.app.state, "app_config_repository", None)
    if app_config_repo:
        eff = await app_config_repo.get_by_owner(ctx.user_id)
        if eff is not None and len(await job_repo.list_by_owner(ctx.user_id)) >= eff.max_jobs_per_owner:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Maximum number of pipelines (jobs) reached for this account.",
                    "code": "job_limit_exceeded",
                },
            )
    try:
        await job_repo.save_job_graph(graph, skip_reference_checks=True)
    except ValidationError as e:
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation failed", "validation_errors": e.errors},
        )
    try:
        await link_repo.attach(trigger_id, job_id, ctx.user_id)
    except TriggerJobLinkPolicyError as e:
        return JSONResponse(
            status_code=422,
            content={"detail": e.message, "code": e.code},
        )
    saved = await job_repo.get_graph_by_id(job_id, ctx.user_id)
    payload = job_graph_to_yaml_dict(saved) if saved else {"id": job_id}
    return await _apply_trigger_links_to_job_payload(
        payload, job_id, ctx.user_id, link_repo
    )


@router.delete("/pipelines/{pipeline_id}")
async def delete_pipeline(
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
    graph = await job_repo.get_graph_by_id(pipeline_id, ctx.user_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    await job_repo.archive(pipeline_id, ctx.user_id)
    return {"status": "archived", "id": pipeline_id}


@router.get("/data-targets")
async def list_data_targets(
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
    targets = await target_repo.list_by_owner(ctx.user_id)
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
async def get_data_target_schema(
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
    target = await target_repo.get_by_id(target_id, ctx.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Data target not found")
    schema = None
    if target.active_schema_snapshot_id:
        schema = await target_schema_repo.get_by_id(target.active_schema_snapshot_id, ctx.user_id)
    if not schema:
        schema = await target_schema_repo.get_active_for_target(target_id, ctx.user_id)
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
async def list_step_templates(
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
    templates = await step_template_repo.list_all()
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
async def get_step_template(
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
    template = await step_template_repo.get_by_id(template_id)
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
async def list_connections(
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
    instances = await conn_repo.list_by_owner(ctx.user_id)
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
async def list_triggers(
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
    triggers = await trigger_repo.list_by_owner(ctx.user_id)
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
async def create_trigger(
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
    existing = await trigger_repo.get_by_path(normalized_path, ctx.user_id)
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
    app_config_repo = getattr(request.app.state, "app_config_repository", None)
    if app_config_repo:
        eff = await app_config_repo.get_by_owner(ctx.user_id)
        if eff is not None and len(trigger_repo.list_by_owner(ctx.user_id)) >= eff.max_triggers_per_owner:
            raise HTTPException(
                status_code=403,
                detail={
                    "message": "Maximum number of triggers reached for this account.",
                    "code": "trigger_limit_exceeded",
                },
            )
    await trigger_repo.save(trigger)
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
async def patch_trigger(
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
    trigger = await trigger_repo.get_by_id(trigger_id, ctx.user_id)
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
    await trigger_repo.save(trigger)
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
async def rotate_trigger_secret(
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
        updated, new_secret = await trigger_repo.rotate_secret(trigger_id, ctx.user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "id": updated.id,
        "secret": new_secret,
        "secret_last_rotated_at": _serialize_datetime(updated.secret_last_rotated_at),
    }


@router.delete("/triggers/{trigger_id}")
async def delete_trigger(
    request: Request,
    trigger_id: str,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Permanently delete an HTTP trigger owned by the authenticated user.
    Trigger–pipeline links are removed; pipelines themselves are not deleted.
    """
    trigger_repo = getattr(request.app.state, "trigger_repository", None)
    if not trigger_repo:
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: trigger repository not available",
        )
    existing = await trigger_repo.get_by_id(trigger_id, ctx.user_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Trigger not found")
    await trigger_repo.delete(trigger_id, ctx.user_id)
    return {"status": "deleted", "id": trigger_id}


@router.get("/account")
async def get_account(
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
    profile = await auth_repo.get_profile(ctx.user_id)
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
        limits = await app_config_repo.get_by_owner(ctx.user_id)
        if limits:
            payload["limits"] = {
                "max_stages_per_job": limits.max_stages_per_job,
                "max_pipelines_per_stage": limits.max_pipelines_per_stage,
                "max_steps_per_pipeline": limits.max_steps_per_pipeline,
                "max_jobs_per_owner": limits.max_jobs_per_owner,
                "max_triggers_per_owner": limits.max_triggers_per_owner,
                "max_runs_per_utc_day": limits.max_runs_per_utc_day,
                "max_runs_per_utc_month": limits.max_runs_per_utc_month,
            }

    return payload


# ---------------------------------------------------------------------------
# Template provisioning
# ---------------------------------------------------------------------------

TEMPLATE_DB_SEARCH_NAME = "Oleo Places Template Database"
TEMPLATE_PIPELINE_DISPLAY_NAME = "Oleo Template Pipeline"
PLACES_TEMPLATE_ALLOWED_EMAIL = "forsythetony@gmail.com"
PLACES_INSERTION_TEMPLATE_JOB_DISPLAY_NAME = "Places Insertion Pipeline [From Template]"
PLACES_INSERTION_TEMPLATE_TRIGGER_DISPLAY_NAME = "Places Trigger [From Template]"
PLACES_INSERTION_TEMPLATE_TRIGGER_PATH = "/places-from-template"
PLACES_INSERTION_TARGET_ID = "target_places_to_visit"
# Cap how many objects we enumerate for TEMPLATE_DB_NOT_FOUND (Notion workspaces can be huge).
_TEMPLATE_ERROR_MAX_DATABASES = 200
_TEMPLATE_ERROR_MAX_PAGES = 100


class _NotionVisibleItem(TypedDict):
    id: str
    title: str


def _build_template_job_graph(
    job_id: str, owner_user_id: str, target_id: str
) -> "JobGraph":
    """Build a trimmed-down job graph for the Oleo Places template database.

    Notion target columns (only these are written): Name, Address, Coordinates, Description.

    Stages:
      1. Research -- optimize query -> Google Places lookup -> cache
      2. Property Setting -- set those four schema properties only

    Stage/pipeline/step IDs are prefixed with *job_id* so this job does not collide with
    the bootstrap Notion Place Inserter graph (same unqualified ids, different sequences under
    ``stage_property_setting``), which would violate ``uq_pipeline_sequence_per_stage``.
    """
    from app.domain.jobs import JobDefinition, PipelineDefinition, StageDefinition, StepInstance
    from app.services.validation_service import JobGraph

    def nid(local: str) -> str:
        return f"{job_id}_{local}"

    sid_stage_research = nid("stage_research")
    sid_stage_ps = nid("stage_property_setting")
    pid_research = nid("pipeline_research")
    pid_name = nid("pipeline_name")
    pid_address = nid("pipeline_address")
    pid_coordinates = nid("pipeline_coordinates")
    pid_description = nid("pipeline_description")

    st_opt = nid("step_optimize_query")
    st_gpl = nid("step_google_places_lookup")
    st_cpl = nid("step_cache_places")
    st_cpo = nid("step_cache_place")
    st_sn = nid("step_property_set_name")
    st_sa = nid("step_property_set_address")
    st_ct = nid("step_coordinates_templater")
    st_sc = nid("step_property_set_coordinates")
    st_dtpl = nid("step_description_templater")
    st_sd = nid("step_property_set_description")

    # --- Stage 1: Research (identical to bootstrap) ---
    steps_research = [
        StepInstance(
            id=st_opt,
            pipeline_id=pid_research,
            step_template_id="step_template_optimize_input_claude",
            display_name="Optimize Query",
            sequence=1,
            input_bindings={"query": {"signal_ref": "trigger.payload.keywords"}},
            config={
                "prompt": "Rewrite this input into an optimized Google Places query.",
                "linked_step_id": st_gpl,
                # Oleo template DB has only four columns — do not inject full target schema into Claude.
                "include_target_query_schema": False,
            },
        ),
        StepInstance(
            id=st_gpl,
            pipeline_id=pid_research,
            step_template_id="step_template_google_places_lookup",
            display_name="Google Places Lookup",
            sequence=2,
            input_bindings={"query": {"signal_ref": f"step.{st_opt}.optimized_query"}},
            config={
                "connector_instance_id": "connector_instance_google_places_default",
                "fetch_details_if_needed": True,
            },
        ),
        StepInstance(
            id=st_cpl,
            pipeline_id=pid_research,
            step_template_id="step_template_cache_set",
            display_name="Cache Search Response",
            sequence=3,
            input_bindings={"value": {"signal_ref": f"step.{st_gpl}.search_response"}},
            config={"cache_key": "google_places_response"},
        ),
        StepInstance(
            id=st_cpo,
            pipeline_id=pid_research,
            step_template_id="step_template_cache_set",
            display_name="Cache Selected Place",
            sequence=4,
            input_bindings={"value": {"signal_ref": f"step.{st_gpl}.selected_place"}},
            config={"cache_key": "google_places_selected_place"},
        ),
    ]

    # --- Stage 2: Property Setting (trimmed for template DB) ---
    step_set_name = StepInstance(
        id=st_sn,
        pipeline_id=pid_name,
        step_template_id="step_template_property_set",
        display_name="Set Name",
        sequence=1,
        input_bindings={"value": {"cache_key_ref": {"cache_key": "google_places_selected_place", "path": "displayName"}}},
        config={"schema_property_id": "prop_name"},
    )
    step_set_address = StepInstance(
        id=st_sa,
        pipeline_id=pid_address,
        step_template_id="step_template_property_set",
        display_name="Set Address",
        sequence=1,
        input_bindings={"value": {"cache_key_ref": {"cache_key": "google_places_selected_place", "path": "formattedAddress"}}},
        config={"schema_property_id": "prop_address"},
    )
    step_coord_templater = StepInstance(
        id=st_ct,
        pipeline_id=pid_coordinates,
        step_template_id="step_template_templater",
        display_name="Format Coordinates",
        sequence=1,
        input_bindings={},
        config={
            "template": "{{latitude}}, {{longitude}}",
            "values": {
                "latitude": {"cache_key_ref": {"cache_key": "google_places_selected_place", "path": "latitude"}},
                "longitude": {"cache_key_ref": {"cache_key": "google_places_selected_place", "path": "longitude"}},
            },
        },
    )
    step_set_coordinates = StepInstance(
        id=st_sc,
        pipeline_id=pid_coordinates,
        step_template_id="step_template_property_set",
        display_name="Set Coordinates",
        sequence=2,
        input_bindings={"value": {"signal_ref": f"step.{st_ct}.rendered_value"}},
        config={"schema_property_id": "prop_coordinates"},
    )
    # Description: Google Places editorial / generative summaries only (no extra AI step).
    step_description_templater = StepInstance(
        id=st_dtpl,
        pipeline_id=pid_description,
        step_template_id="step_template_templater",
        display_name="Place summaries to text",
        sequence=1,
        input_bindings={},
        config={
            "template": "{{generative}}{{editorial}}",
            "values": {
                "generative": {
                    "cache_key_ref": {"cache_key": "google_places_selected_place", "path": "generativeSummary"}
                },
                "editorial": {
                    "cache_key_ref": {"cache_key": "google_places_selected_place", "path": "editorialSummary"}
                },
            },
        },
    )
    step_set_description = StepInstance(
        id=st_sd,
        pipeline_id=pid_description,
        step_template_id="step_template_property_set",
        display_name="Set Description",
        sequence=2,
        input_bindings={"value": {"signal_ref": f"step.{st_dtpl}.rendered_value"}},
        config={"schema_property_id": "prop_description"},
    )

    steps_property = [
        step_set_name, step_set_address,
        step_coord_templater, step_set_coordinates,
        step_description_templater, step_set_description,
    ]

    # Pipelines
    pipeline_research = PipelineDefinition(
        id=pid_research, stage_id=sid_stage_research,
        display_name="Research Pipeline", sequence=1,
        step_ids=[s.id for s in steps_research],
    )
    pipeline_name = PipelineDefinition(
        id=pid_name, stage_id=sid_stage_ps,
        display_name="Set Name", sequence=1, step_ids=[st_sn],
    )
    pipeline_address = PipelineDefinition(
        id=pid_address, stage_id=sid_stage_ps,
        display_name="Set Address", sequence=2, step_ids=[st_sa],
    )
    pipeline_coordinates = PipelineDefinition(
        id=pid_coordinates, stage_id=sid_stage_ps,
        display_name="Set Coordinates", sequence=3,
        step_ids=[st_ct, st_sc],
    )
    pipeline_description = PipelineDefinition(
        id=pid_description, stage_id=sid_stage_ps,
        display_name="Set Description", sequence=4,
        step_ids=[st_dtpl, st_sd],
    )

    prop_pipelines = [pipeline_name, pipeline_address, pipeline_coordinates, pipeline_description]

    # Stages
    stage_research = StageDefinition(
        id=sid_stage_research, job_id=job_id, display_name="Research",
        sequence=1, pipeline_ids=[pid_research], pipeline_run_mode="sequential",
    )
    stage_property_setting = StageDefinition(
        id=sid_stage_ps, job_id=job_id, display_name="Property Setting",
        sequence=2, pipeline_ids=[p.id for p in prop_pipelines], pipeline_run_mode="sequential",
    )

    job = JobDefinition(
        id=job_id,
        owner_user_id=owner_user_id,
        display_name=TEMPLATE_PIPELINE_DISPLAY_NAME,
        target_id=target_id,
        status="active",
        stage_ids=[sid_stage_research, sid_stage_ps],
    )

    return JobGraph(
        job=job,
        stages=[stage_research, stage_property_setting],
        pipelines=[pipeline_research] + prop_pipelines,
        steps=steps_research + steps_property,
    )


def _notion_data_source_or_database_display_name(item: dict[str, Any]) -> str:
    """Display name for Notion search results with object database or data_source."""
    name = (item.get("name") or "").strip()
    if name:
        return name
    title_arr = item.get("title") or []
    if isinstance(title_arr, list):
        name = "".join(
            b.get("plain_text", "") or b.get("text", {}).get("content", "")
            for b in title_arr
            if isinstance(b, dict)
        )
    return name.strip() or "Untitled"


async def _search_notion_database(token: str, query: str) -> tuple[str, str] | None:
    """Search Notion for a database / data source whose title matches *query* (substring).

    Uses ``filter: data_source`` (Notion API 2025-09-03+): ``filter: database`` often returns
    nothing even when the workspace has shared databases; ``data_source`` matches
    ``refresh_sources`` / connector discovery.

    Returns ``(data_source_id, display_name)`` or None.
    """
    from app.services.notion_oauth_service import NOTION_API_VERSION

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.notion.com/v1/search",
            json={
                "query": query,
                "filter": {"property": "object", "value": "data_source"},
            },
            headers=headers,
            timeout=30,
        )
    if r.status_code != 200:
        logger.warning("template_notion_search_failed | status={}", r.status_code)
        return None

    q = query.lower()
    for item in r.json().get("results", []):
        if not isinstance(item, dict):
            continue
        obj = item.get("object")
        if obj not in ("database", "data_source"):
            continue
        name = _notion_data_source_or_database_display_name(item)
        if q not in name.lower():
            continue
        item_id = item.get("id")
        if not item_id:
            continue
        if obj == "data_source":
            return item_id, name
        data_source_id = await _resolve_data_source_id(token, item_id)
        if data_source_id:
            return data_source_id, name
    return None


def _notion_search_item_display_title(item: dict[str, Any]) -> str:
    """Best-effort title from a Notion /search result item (database, data_source, or page)."""
    obj = item.get("object")
    if obj in ("database", "data_source"):
        return _notion_data_source_or_database_display_name(item)
    if obj == "page":
        props = item.get("properties") or {}
        if isinstance(props, dict):
            for prop in props.values():
                if not isinstance(prop, dict) or prop.get("type") != "title":
                    continue
                parts = prop.get("title") or []
                if isinstance(parts, list):
                    name = "".join(
                        b.get("plain_text", "") or b.get("text", {}).get("content", "")
                        for b in parts
                        if isinstance(b, dict)
                    )
                    return name.strip() or "Untitled page"
        return "Untitled page"
    return "Untitled"


async def _list_notion_search_by_filter(
    token: str,
    object_filter: Literal["data_source", "page"],
    *,
    max_items: int | None = None,
) -> tuple[list[_NotionVisibleItem], bool]:
    """Paginate Notion /v1/search (no query = all objects the integration can access).

    Returns (items, truncated) where truncated is True if stopped early due to *max_items*.
    """
    from app.services.notion_oauth_service import NOTION_API_VERSION

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }
    items: list[_NotionVisibleItem] = []
    seen_ids: set[str] = set()
    cursor: str | None = None
    async with httpx.AsyncClient() as client:
        while True:
            if max_items is not None and len(items) >= max_items:
                return items, True
            page_size = 100
            if max_items is not None:
                page_size = min(100, max_items - len(items))
            body: dict[str, Any] = {
                "filter": {"property": "object", "value": object_filter},
                "page_size": page_size,
            }
            if cursor:
                body["start_cursor"] = cursor
            r = await client.post(
                "https://api.notion.com/v1/search",
                json=body,
                headers=headers,
                timeout=60,
            )
            if r.status_code != 200:
                logger.warning(
                    "template_notion_list_failed | filter={} status={}",
                    object_filter,
                    r.status_code,
                )
                return items, False

            payload = r.json()
            for item in payload.get("results") or []:
                if not isinstance(item, dict):
                    continue
                if object_filter == "data_source":
                    obj = item.get("object")
                    if obj not in ("database", "data_source"):
                        continue
                oid = item.get("id")
                if not oid or oid in seen_ids:
                    continue
                seen_ids.add(oid)
                items.append(
                    {
                        "id": oid,
                        "title": _notion_search_item_display_title(item),
                    }
                )
                if max_items is not None and len(items) >= max_items:
                    return items, True

            if not payload.get("has_more"):
                break
            cursor = payload.get("next_cursor")
            if not cursor:
                break
    return items, False


def _format_template_db_not_found_detail(
    databases: list[_NotionVisibleItem],
    pages: list[_NotionVisibleItem],
    databases_truncated: bool,
    pages_truncated: bool,
) -> str:
    lines = [
        f"Could not find a database named '{TEMPLATE_DB_SEARCH_NAME}' in your Notion workspace. "
        "The quick-start search matches that phrase as a substring of the database title. "
        "Make sure a database with that name exists and is shared with the Oleo integration.",
        "",
    ]
    if databases:
        suffix = f" ({len(databases)}"
        suffix += ", list truncated" if databases_truncated else ""
        suffix += ")"
        lines.append(
            f"Databases / data sources this integration can access{suffix} "
            f"(Notion API lists these via the data_source search filter):"
        )
        for d in databases:
            lines.append(f"  • {d['title']}")
    else:
        lines.append(
            "Databases / data sources this integration can access: none listed — "
            "share at least one database with the integration (Connections → Notion, "
            "then “Add connections” on the database). If you already shared one, "
            "Notion’s API may still be catching up; try again in a minute."
        )
    lines.append("")
    if pages:
        suffix = f" (showing {len(pages)}"
        suffix += ", list truncated" if pages_truncated else ""
        suffix += ")"
        lines.append(f"Pages this integration can access{suffix}:")
        for p in pages:
            lines.append(f"  • {p['title']}")
    else:
        lines.append("Pages this integration can access: none listed.")
    return "\n".join(lines)


async def _resolve_data_source_id(token: str, database_id: str) -> str | None:
    """Resolve a Notion database_id to its data_source_id for page creation."""
    from app.services.notion_oauth_service import NOTION_API_VERSION

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://api.notion.com/v1/databases/{database_id}",
            headers=headers,
            timeout=30,
        )
    if r.status_code != 200:
        return None
    data_sources = r.json().get("data_sources") or []
    if not data_sources:
        return None
    return data_sources[0].get("id")


@router.post("/bootstrap/create-from-template")
async def create_pipeline_from_template(
    request: Request,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Idempotent one-click provisioning: searches Notion for the Oleo Places
    Template Database, creates a data target + /hello-world trigger + trimmed
    pipeline. Safe to call repeatedly.
    """
    # --- repos ---
    notion_oauth = getattr(request.app.state, "notion_oauth_service", None)
    trigger_repo = getattr(request.app.state, "trigger_repository", None)
    job_repo = getattr(request.app.state, "job_repository", None)
    target_repo = getattr(request.app.state, "target_repository", None)
    link_repo = getattr(request.app.state, "trigger_job_link_repository", None)
    schema_sync = getattr(request.app.state, "schema_sync_service", None)

    for name, repo in [
        ("notion_oauth_service", notion_oauth),
        ("trigger_repository", trigger_repo),
        ("job_repository", job_repo),
        ("target_repository", target_repo),
        ("trigger_job_link_repository", link_repo),
        ("schema_sync_service", schema_sync),
    ]:
        if repo is None:
            return JSONResponse(status_code=500, content={"detail": f"Server misconfiguration: {name} not available"})

    # --- idempotency: check existing job ---
    existing_jobs = await job_repo.list_by_owner(ctx.user_id)
    existing_job = next((j for j in existing_jobs if j.display_name == TEMPLATE_PIPELINE_DISPLAY_NAME), None)
    if existing_job:
        existing_trigger = await trigger_repo.get_by_path("/hello-world", ctx.user_id)
        return {
            "status": "already_exists",
            "job_id": existing_job.id,
            "trigger_id": existing_trigger.id if existing_trigger else None,
            "trigger_path": "/hello-world",
            "trigger_secret": None,
            "target_id": existing_job.target_id,
            "message": "Template pipeline already exists.",
        }

    # --- 1. verify Notion connected ---
    token = await notion_oauth.get_access_token(ctx.user_id)
    if not token:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Notion not connected. Please connect Notion first on the Connections page.",
                "code": "NOTION_NOT_CONNECTED",
            },
        )

    # --- 2. search for template database ---
    result = await _search_notion_database(token, TEMPLATE_DB_SEARCH_NAME)
    if not result:
        visible_databases, databases_truncated = await _list_notion_search_by_filter(
            token, "data_source", max_items=_TEMPLATE_ERROR_MAX_DATABASES
        )
        visible_pages, pages_truncated = await _list_notion_search_by_filter(
            token, "page", max_items=_TEMPLATE_ERROR_MAX_PAGES
        )
        detail = _format_template_db_not_found_detail(
            visible_databases, visible_pages, databases_truncated, pages_truncated
        )
        return JSONResponse(
            status_code=404,
            content={
                "detail": detail,
                "code": "TEMPLATE_DB_NOT_FOUND",
                "visible_databases": visible_databases,
                "visible_pages": visible_pages,
                "visible_databases_truncated": databases_truncated,
                "visible_pages_truncated": pages_truncated,
            },
        )
    data_source_id, db_title = result

    # --- 3. create or reuse DataTarget (data_source_id from _search_notion_database) ---
    from app.domain.targets import DataTarget

    target_id = f"target_notion_{data_source_id.replace('-', '_')[:20]}"
    existing_target = await target_repo.get_by_id(target_id, ctx.user_id)
    if not existing_target:
        target = DataTarget(
            id=target_id,
            owner_user_id=ctx.user_id,
            target_template_id="notion_database",
            connector_instance_id="connector_instance_notion_default",
            display_name=db_title,
            external_target_id=data_source_id,
            status="active",
        )
        await target_repo.save(target)

    # --- 5. sync schema ---
    try:
        await schema_sync.sync_for_target(target_id, ctx.user_id)
    except Exception as e:
        logger.warning("template_schema_sync_failed | target={} error={}", target_id, e)

    # --- 6. create or reuse /hello-world trigger ---
    existing_trigger = await trigger_repo.get_by_path("/hello-world", ctx.user_id)
    trigger_secret_plaintext = None
    if existing_trigger:
        trigger_id = existing_trigger.id
    else:
        trigger_id = f"trigger_{uuid.uuid4().hex[:12]}"
        trigger_secret_plaintext = secrets.token_hex(15)
        now = datetime.now(timezone.utc)
        trigger = TriggerDefinition(
            id=trigger_id,
            owner_user_id=ctx.user_id,
            trigger_type="http",
            display_name="Hello World",
            path="/hello-world",
            method="POST",
            request_body_schema=default_keywords_request_body_schema(),
            status="active",
            auth_mode="bearer",
            secret_value=trigger_secret_plaintext,
            secret_last_rotated_at=now,
            visibility="owner",
            created_at=now,
            updated_at=now,
        )
        await trigger_repo.save(trigger)

    # --- 7. build + save job graph ---
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    graph = _build_template_job_graph(job_id, ctx.user_id, target_id)

    try:
        await job_repo.save_job_graph(graph, skip_reference_checks=True)
    except ValidationError as e:
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation failed", "validation_errors": e.errors},
        )

    # --- 8. link trigger to job ---
    try:
        await link_repo.attach(trigger_id, job_id, ctx.user_id)
    except TriggerJobLinkPolicyError as e:
        return JSONResponse(
            status_code=422,
            content={"detail": e.message, "code": e.code},
        )

    logger.info(
        "template_pipeline_created | user_id={} job_id={} trigger_id={} target_id={}",
        ctx.user_id, job_id, trigger_id, target_id,
    )

    return {
        "status": "created",
        "job_id": job_id,
        "trigger_id": trigger_id,
        "trigger_path": "/hello-world",
        "trigger_secret": trigger_secret_plaintext,
        "target_id": target_id,
        "target_display_name": db_title,
        "message": "Template pipeline created successfully.",
    }


@router.post("/bootstrap/create-places-insertion-from-template")
async def create_places_insertion_from_template(
    request: Request,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Email-gated: provisions a full clone of ``notion_place_inserter.yaml`` (research + property
    stages) against ``target_places_to_visit``, plus HTTP trigger
    ``PLACES_INSERTION_TEMPLATE_TRIGGER_PATH``. Idempotent per job display name.
    """
    if (ctx.email or "").lower() != PLACES_TEMPLATE_ALLOWED_EMAIL.lower():
        return JSONResponse(
            status_code=403,
            content={
                "detail": "This action is not available for your account.",
                "code": "PLACES_TEMPLATE_FORBIDDEN",
            },
        )

    notion_oauth = getattr(request.app.state, "notion_oauth_service", None)
    trigger_repo = getattr(request.app.state, "trigger_repository", None)
    job_repo = getattr(request.app.state, "job_repository", None)
    target_repo = getattr(request.app.state, "target_repository", None)
    link_repo = getattr(request.app.state, "trigger_job_link_repository", None)
    schema_sync = getattr(request.app.state, "schema_sync_service", None)

    for name, repo in [
        ("notion_oauth_service", notion_oauth),
        ("trigger_repository", trigger_repo),
        ("job_repository", job_repo),
        ("target_repository", target_repo),
        ("trigger_job_link_repository", link_repo),
        ("schema_sync_service", schema_sync),
    ]:
        if repo is None:
            return JSONResponse(
                status_code=500,
                content={"detail": f"Server misconfiguration: {name} not available"},
            )

    existing_jobs = await job_repo.list_by_owner(ctx.user_id)
    existing_job = next(
        (j for j in existing_jobs if j.display_name == PLACES_INSERTION_TEMPLATE_JOB_DISPLAY_NAME),
        None,
    )
    if existing_job:
        existing_trigger = await trigger_repo.get_by_path(
            PLACES_INSERTION_TEMPLATE_TRIGGER_PATH, ctx.user_id
        )
        tgt = await target_repo.get_by_id(PLACES_INSERTION_TARGET_ID, ctx.user_id)
        return {
            "status": "already_exists",
            "job_id": existing_job.id,
            "trigger_id": existing_trigger.id if existing_trigger else None,
            "trigger_path": PLACES_INSERTION_TEMPLATE_TRIGGER_PATH,
            "trigger_secret": None,
            "target_id": existing_job.target_id,
            "target_display_name": getattr(tgt, "display_name", None) if tgt else None,
            "message": "Places insertion template pipeline already exists.",
        }

    token = await notion_oauth.get_access_token(ctx.user_id)
    if not token:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Notion not connected. Please connect Notion first on the Connections page.",
                "code": "NOTION_NOT_CONNECTED",
            },
        )

    places_target = await target_repo.get_by_id(PLACES_INSERTION_TARGET_ID, ctx.user_id)
    if not places_target:
        return JSONResponse(
            status_code=422,
            content={
                "detail": (
                    "Bootstrap target 'Places to Visit' is missing. "
                    "Complete normal account provisioning first (e.g. first-time trigger setup)."
                ),
                "code": "TARGET_PLACES_NOT_PROVISIONED",
            },
        )

    try:
        await schema_sync.sync_for_target(PLACES_INSERTION_TARGET_ID, ctx.user_id)
    except Exception as e:
        logger.warning(
            "places_insertion_template_schema_sync_failed | target={} error={}",
            PLACES_INSERTION_TARGET_ID,
            e,
        )

    job_data = load_yaml_file("product_model/bootstrap/jobs/notion_place_inserter.yaml")
    if not job_data:
        return JSONResponse(
            status_code=500,
            content={"detail": "Bundled job definition not found."},
        )

    try:
        base_graph = parse_job_graph(job_data, owner_user_id_override=ctx.user_id)
    except Exception as e:
        logger.exception("places_insertion_template_parse_failed | error={}", e)
        return JSONResponse(
            status_code=500,
            content={"detail": "Failed to parse bundled job definition."},
        )

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    graph = clone_job_graph_with_prefixed_ids(
        base_graph,
        job_id,
        owner_user_id=ctx.user_id,
        display_name=PLACES_INSERTION_TEMPLATE_JOB_DISPLAY_NAME,
        target_id=PLACES_INSERTION_TARGET_ID,
    )

    try:
        await job_repo.save_job_graph(graph, skip_reference_checks=True)
    except ValidationError as e:
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation failed", "validation_errors": e.errors},
        )

    existing_trigger = await trigger_repo.get_by_path(
        PLACES_INSERTION_TEMPLATE_TRIGGER_PATH, ctx.user_id
    )
    trigger_secret_plaintext = None
    if existing_trigger:
        trigger_id = existing_trigger.id
    else:
        trigger_id = f"trigger_{uuid.uuid4().hex[:12]}"
        trigger_secret_plaintext = secrets.token_hex(15)
        now = datetime.now(timezone.utc)
        trigger = TriggerDefinition(
            id=trigger_id,
            owner_user_id=ctx.user_id,
            trigger_type="http",
            display_name=PLACES_INSERTION_TEMPLATE_TRIGGER_DISPLAY_NAME,
            path=PLACES_INSERTION_TEMPLATE_TRIGGER_PATH,
            method="POST",
            request_body_schema=default_keywords_request_body_schema(),
            status="active",
            auth_mode="bearer",
            secret_value=trigger_secret_plaintext,
            secret_last_rotated_at=now,
            visibility="owner",
            created_at=now,
            updated_at=now,
        )
        await trigger_repo.save(trigger)

    try:
        await link_repo.attach(trigger_id, job_id, ctx.user_id)
    except TriggerJobLinkPolicyError as e:
        return JSONResponse(
            status_code=422,
            content={"detail": e.message, "code": e.code},
        )

    logger.info(
        "places_insertion_template_created | user_id={} job_id={} trigger_id={} target_id={}",
        ctx.user_id,
        job_id,
        trigger_id,
        PLACES_INSERTION_TARGET_ID,
    )

    return {
        "status": "created",
        "job_id": job_id,
        "trigger_id": trigger_id,
        "trigger_path": PLACES_INSERTION_TEMPLATE_TRIGGER_PATH,
        "trigger_secret": trigger_secret_plaintext,
        "target_id": PLACES_INSERTION_TARGET_ID,
        "target_display_name": places_target.display_name,
        "message": "Places insertion template pipeline created successfully.",
    }
