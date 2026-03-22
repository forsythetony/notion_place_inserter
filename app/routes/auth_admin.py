"""Admin-only auth directory: user profiles and cohorts."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import AuthContext, require_admin_managed_auth
from app.domain.runs import JobRun, PipelineRun, StageRun, StepRun, UsageRecord
from app.domain.limits import AppLimits
from app.services.effective_limits import (
    LimitsResolutionError,
    limits_resolution_summary,
    resolve_effective_app_limits,
)
from app.services.supabase_auth_repository import SupabaseAuthRepository
from app.services.usage_cost_estimation_service import (
    RateCardRow,
    estimate_usage_record_usd,
    parse_rate_card_rows,
    sum_estimated_usd,
)

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


def _dt_iso(val: datetime | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _run_repo_or_501(request: Request):
    repo = getattr(request.app.state, "supabase_run_repository", None)
    if repo is None:
        raise HTTPException(
            status_code=501,
            detail="Admin run explorer requires Postgres run repository",
        )
    return repo


def _job_run_admin_dict(run: JobRun) -> dict:
    return {
        "id": run.id,
        "ownerUserId": run.owner_user_id,
        "jobId": run.job_id,
        "triggerId": run.trigger_id,
        "targetId": run.target_id,
        "status": run.status,
        "triggerPayload": run.trigger_payload or {},
        "definitionSnapshotRef": run.definition_snapshot_ref,
        "platformJobId": run.platform_job_id,
        "retryCount": run.retry_count,
        "startedAt": _dt_iso(run.started_at),
        "completedAt": _dt_iso(run.completed_at),
        "errorSummary": run.error_summary,
        "resultJson": run.result_json,
        "createdAt": _dt_iso(run.created_at),
    }


def _load_rate_card_rows(request: Request) -> list[RateCardRow]:
    client = getattr(request.app.state, "supabase_client", None)
    if client is None:
        return []
    try:
        r = client.table("usage_rate_cards").select("*").execute()
        return parse_rate_card_rows(r.data or [])
    except Exception as e:
        logger.warning("usage_rate_cards_load_failed | error={}", e)
        return []


def _usage_rollups_from_records(
    records: list[UsageRecord],
    rate_rows: list[RateCardRow] | None = None,
) -> dict:
    totals = {"llmTokens": 0, "externalApiCalls": 0}
    by_provider: dict[str, dict[str, int]] = {}
    for ur in records:
        p = ur.provider
        if p not in by_provider:
            by_provider[p] = {"llmTokens": 0, "externalApiCalls": 0}
        if ur.usage_type == "llm_tokens":
            v = int(ur.metric_value)
            totals["llmTokens"] += v
            by_provider[p]["llmTokens"] += v
        elif ur.usage_type == "external_api_call":
            v = int(ur.metric_value)
            totals["externalApiCalls"] += v
            by_provider[p]["externalApiCalls"] += v
    out: dict = {"totals": totals, "byProvider": by_provider}
    if rate_rows is not None:
        out["estimatedCostUsd"] = round(sum_estimated_usd(records, rate_rows), 6)
    return out


def _usage_record_admin_dict(u: UsageRecord, *, estimated_cost_usd: float | None = None) -> dict:
    d = {
        "id": u.id,
        "jobRunId": u.job_run_id,
        "usageType": u.usage_type,
        "provider": u.provider,
        "metricName": u.metric_name,
        "metricValue": u.metric_value,
        "ownerUserId": u.owner_user_id,
        "stepRunId": u.step_run_id,
        "metadata": u.metadata,
        "createdAt": _dt_iso(u.created_at),
    }
    if estimated_cost_usd is not None:
        d["estimatedCostUsd"] = round(estimated_cost_usd, 6)
    return d


def _stage_run_admin_dict(s: StageRun) -> dict:
    return {
        "id": s.id,
        "jobRunId": s.job_run_id,
        "stageId": s.stage_id,
        "status": s.status,
        "ownerUserId": s.owner_user_id,
        "startedAt": _dt_iso(s.started_at),
        "completedAt": _dt_iso(s.completed_at),
    }


def _pipeline_run_admin_dict(p: PipelineRun) -> dict:
    return {
        "id": p.id,
        "stageRunId": p.stage_run_id,
        "pipelineId": p.pipeline_id,
        "jobRunId": p.job_run_id,
        "status": p.status,
        "ownerUserId": p.owner_user_id,
        "startedAt": _dt_iso(p.started_at),
        "completedAt": _dt_iso(p.completed_at),
    }


def _step_run_admin_dict(s: StepRun) -> dict:
    return {
        "id": s.id,
        "pipelineRunId": s.pipeline_run_id,
        "stepId": s.step_id,
        "stepTemplateId": s.step_template_id,
        "jobRunId": s.job_run_id,
        "stageRunId": s.stage_run_id,
        "pipelineId": s.pipeline_id,
        "status": s.status,
        "inputSummary": s.input_summary,
        "outputSummary": s.output_summary,
        "stepTraceFull": s.step_trace_full,
        "processingLog": s.processing_log or [],
        "startedAt": _dt_iso(s.started_at),
        "completedAt": _dt_iso(s.completed_at),
        "errorSummary": s.error_summary,
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


@router.get("/usage-providers")
def list_usage_providers_admin(
    request: Request,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    """Catalog rows for usage_records.provider labels (YAML-seeded)."""
    client = getattr(request.app.state, "supabase_client", None)
    if client is None:
        raise HTTPException(status_code=501, detail="Supabase client not configured")
    logger.info("admin_list_usage_providers | admin_user_id={}", ctx.user_id)
    try:
        r = client.table("usage_provider_definitions").select("*").order("provider_id").execute()
    except Exception as e:
        logger.exception("admin_list_usage_providers_failed | error={}", e)
        raise HTTPException(
            status_code=503,
            detail="Failed to load usage provider definitions (migration applied?)",
        ) from e
    items = []
    for row in r.data or []:
        items.append(
            {
                "providerId": row["provider_id"],
                "displayName": row.get("display_name"),
                "description": row.get("description") or "",
                "billingUnit": row.get("billing_unit") or "call",
                "notes": row.get("notes"),
                "createdAt": row.get("created_at"),
                "updatedAt": row.get("updated_at"),
            }
        )
    return {"items": items}


@router.get("/runs")
def list_recent_runs_admin(
    request: Request,
    ctx: AuthContext = Depends(require_admin_managed_auth),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    from_ts: str | None = Query(None, alias="from"),
    to_ts: str | None = Query(None, alias="to"),
    user_ids: list[str] | None = Query(
        None,
        description="Repeat this query param to restrict runs to these owner user ids (UUIDs).",
    ),
):
    """Paginated recent job runs across all users with structure counts and usage rollups per run."""
    run_repo = _run_repo_or_501(request)
    owner_filter = user_ids if user_ids else None
    logger.info(
        "admin_list_recent_runs | admin_user_id={} limit={} offset={}",
        ctx.user_id,
        limit,
        offset,
    )
    runs = run_repo.list_recent_job_runs(
        limit=limit,
        offset=offset,
        from_iso=from_ts,
        to_iso=to_ts,
        owner_user_ids=owner_filter,
    )
    rate_rows = _load_rate_card_rows(request)
    items = []
    for jr in runs:
        uid = jr.owner_user_id
        counts = run_repo.count_run_structure_for_job_run(jr.id, uid)
        usage_rows = run_repo.list_usage_records_for_job_run(jr.id, uid)
        items.append(
            {
                "userId": uid,
                "jobRun": _job_run_admin_dict(jr),
                "counts": {
                    "stages": counts["stages"],
                    "pipelines": counts["pipelines"],
                    "steps": counts["steps"],
                },
                "usageRollups": _usage_rollups_from_records(usage_rows, rate_rows),
            }
        )
    next_offset = offset + len(runs)
    has_more = len(runs) == limit
    return {
        "items": items,
        "nextOffset": next_offset if has_more else None,
        "hasMore": has_more,
    }


@router.get("/users/{user_id}/runs")
def list_user_runs_admin(
    request: Request,
    user_id: UUID,
    ctx: AuthContext = Depends(require_admin_managed_auth),
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    from_ts: str | None = Query(None, alias="from"),
    to_ts: str | None = Query(None, alias="to"),
):
    """Paginated job runs for a user with structure counts and usage rollups per run."""
    uid = str(user_id)
    run_repo = _run_repo_or_501(request)
    logger.info(
        "admin_list_user_runs | admin_user_id={} target_user_id={} limit={} offset={}",
        ctx.user_id,
        uid,
        limit,
        offset,
    )
    runs = run_repo.list_job_runs_by_owner(
        uid,
        limit=limit,
        offset=offset,
        from_iso=from_ts,
        to_iso=to_ts,
    )
    rate_rows = _load_rate_card_rows(request)
    items = []
    for jr in runs:
        counts = run_repo.count_run_structure_for_job_run(jr.id, uid)
        usage_rows = run_repo.list_usage_records_for_job_run(jr.id, uid)
        items.append(
            {
                "jobRun": _job_run_admin_dict(jr),
                "counts": {
                    "stages": counts["stages"],
                    "pipelines": counts["pipelines"],
                    "steps": counts["steps"],
                },
                "usageRollups": _usage_rollups_from_records(usage_rows, rate_rows),
            }
        )
    next_offset = offset + len(runs)
    has_more = len(runs) == limit
    return {
        "userId": uid,
        "items": items,
        "nextOffset": next_offset if has_more else None,
        "hasMore": has_more,
    }


@router.get("/users/{user_id}/runs/{job_run_id}")
def get_user_run_detail_admin(
    request: Request,
    user_id: UUID,
    job_run_id: UUID,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    """Single job run with stages, pipelines, steps, usage_records, and rollups."""
    uid = str(user_id)
    jrid = str(job_run_id)
    run_repo = _run_repo_or_501(request)
    logger.info(
        "admin_get_user_run_detail | admin_user_id={} target_user_id={} job_run_id={}",
        ctx.user_id,
        uid,
        jrid,
    )
    jr = run_repo.get_job_run(jrid, uid)
    if jr is None:
        raise HTTPException(status_code=404, detail="Job run not found for this user")
    counts = run_repo.count_run_structure_for_job_run(jrid, uid)
    usage_rows = run_repo.list_usage_records_for_job_run(jrid, uid)
    stages = run_repo.list_stage_runs_for_job_run(jrid, uid)
    pipelines = run_repo.list_pipeline_run_executions_for_job_run(jrid, uid)
    steps = run_repo.list_step_runs_for_job_run(jrid, uid)
    rate_rows = _load_rate_card_rows(request)
    return {
        "userId": uid,
        "jobRun": _job_run_admin_dict(jr),
        "counts": {
            "stages": counts["stages"],
            "pipelines": counts["pipelines"],
            "steps": counts["steps"],
        },
        "usageRollups": _usage_rollups_from_records(usage_rows, rate_rows),
        "usageRecords": [
            _usage_record_admin_dict(
                u,
                estimated_cost_usd=estimate_usage_record_usd(u, rate_rows),
            )
            for u in usage_rows
        ],
        "stageRuns": [_stage_run_admin_dict(s) for s in stages],
        "pipelineRunExecutions": [_pipeline_run_admin_dict(p) for p in pipelines],
        "stepRuns": [_step_run_admin_dict(s) for s in steps],
    }


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
