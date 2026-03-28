"""Admin-only auth directory: user profiles and cohorts."""

import base64
import json
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
from app.repositories.supabase_beta_waitlist_repository import (
    WAITLIST_ADMIN_SORTS,
    SupabaseBetaWaitlistRepository,
)
from app.routes.invitations import _issue_response_body
from app.services.supabase_auth_repository import SupabaseAuthRepository, USER_TYPES
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
        "betaWaveId": str(row["beta_wave_id"]) if row.get("beta_wave_id") else None,
        "betaWaveKey": row.get("beta_wave_key"),
        "eulaVersionId": str(row["eula_version_id"])
        if row.get("eula_version_id")
        else None,
        "eulaAcceptedAt": row.get("eula_accepted_at"),
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


async def _load_rate_card_rows(request: Request) -> list[RateCardRow]:
    client = getattr(request.app.state, "supabase_client", None)
    if client is None:
        return []
    try:
        r = await client.table("usage_rate_cards").select("*").execute()
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


def _stage_run_admin_dict(
    s: StageRun, stage_run_mode_map: dict[str, str] | None = None
) -> dict:
    d: dict = {
        "id": s.id,
        "jobRunId": s.job_run_id,
        "stageId": s.stage_id,
        "status": s.status,
        "ownerUserId": s.owner_user_id,
        "startedAt": _dt_iso(s.started_at),
        "completedAt": _dt_iso(s.completed_at),
    }
    if stage_run_mode_map:
        d["pipelineRunMode"] = stage_run_mode_map.get(s.stage_id, "parallel")
    return d


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
        "errorDetail": s.error_detail,
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
async def list_user_profiles_admin(
    request: Request,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    logger.info(
        "admin_list_user_profiles | admin_user_id={}",
        ctx.user_id,
    )
    rows = await auth_repo.list_user_profiles_for_admin()
    return {"items": [_profile_row_to_item(r) for r in rows]}


class CohortCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str = Field(..., min_length=1)
    description: str | None = None


class CohortPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None


@router.get("/cohorts")
async def list_cohorts_admin(
    request: Request,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    logger.info("admin_list_cohorts | admin_user_id={}", ctx.user_id)
    rows = await auth_repo.list_cohorts()
    return {"items": [_cohort_row_to_item(r) for r in rows]}


@router.post("/cohorts", status_code=201)
async def create_cohort_admin(
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
        row = await auth_repo.create_cohort(body.key, body.description)
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
async def patch_cohort_admin(
    request: Request,
    cohort_id: UUID,
    body: CohortPatchRequest,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    updated = await auth_repo.update_cohort_description(cohort_id, body.description)
    if updated is None:
        raise HTTPException(status_code=404, detail="Cohort not found")
    logger.info(
        "admin_patch_cohort | admin_user_id={} cohort_id={}",
        ctx.user_id,
        cohort_id,
    )
    return _cohort_row_to_item(updated)


@router.delete("/cohorts/{cohort_id}", status_code=204)
async def delete_cohort_admin(
    request: Request,
    cohort_id: UUID,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    result = await auth_repo.delete_cohort_if_unused(cohort_id)
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


WAITLIST_STATUSES = frozenset(
    {
        "PENDING_REVIEW",
        "SHORTLISTED",
        "INVITED",
        "DECLINED",
        "SPAM",
    }
)


def _decode_waitlist_cursor(cursor: str | None) -> int:
    if not cursor or not cursor.strip():
        return 0
    try:
        raw_b64 = cursor.strip() + "=" * (-len(cursor.strip()) % 4)
        raw = base64.urlsafe_b64decode(raw_b64.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        offset = int(data.get("o", 0))
        return max(0, offset)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Invalid cursor",
        ) from e


def _encode_waitlist_cursor(offset: int) -> str:
    return (
        base64.urlsafe_b64encode(json.dumps({"o": offset}).encode())
        .decode("ascii")
        .rstrip("=")
    )


def _beta_wave_row_to_item(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "key": row["key"],
        "label": row["label"],
        "description": row.get("description"),
        "sortOrder": row.get("sort_order", 0),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }


def _waitlist_row_to_item(row: dict, notion_preview_len: int = 120) -> dict:
    nuc = row.get("notion_use_case") or ""
    preview = (
        nuc
        if len(nuc) <= notion_preview_len
        else nuc[: notion_preview_len - 1] + "…"
    )
    return {
        "id": str(row["id"]),
        "email": row.get("email"),
        "emailNormalized": row.get("email_normalized"),
        "name": row.get("name"),
        "heardAbout": row.get("heard_about"),
        "heardAboutOther": row.get("heard_about_other"),
        "workRole": row.get("work_role"),
        "notionUseCase": row.get("notion_use_case"),
        "notionUseCasePreview": preview,
        "status": row.get("status"),
        "submissionCount": row.get("submission_count"),
        "firstSubmittedAt": row.get("first_submitted_at"),
        "lastSubmittedAt": row.get("last_submitted_at"),
        "invitationCodeId": str(row["invitation_code_id"])
        if row.get("invitation_code_id")
        else None,
        "invitedAt": row.get("invited_at"),
        "reviewedAt": row.get("reviewed_at"),
        "adminNotes": row.get("admin_notes"),
        "betaWaveId": str(row["beta_wave_id"]) if row.get("beta_wave_id") else None,
        "betaWaveKey": row.get("beta_wave_key"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }


@router.get("/beta-waves")
async def list_beta_waves_admin(
    request: Request,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    logger.info("admin_list_beta_waves | admin_user_id={}", ctx.user_id)
    rows = await auth_repo.list_beta_waves()
    return {"items": [_beta_wave_row_to_item(r) for r in rows]}


class WaveCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    key: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    description: str | None = None
    sort_order: int | None = Field(None, alias="sortOrder")


class WavePatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    label: str = Field(..., min_length=1)
    description: str | None = None
    sort_order: int = Field(..., alias="sortOrder")


@router.post("/beta-waves", status_code=201)
async def create_beta_wave_admin(
    request: Request,
    body: WaveCreateRequest,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    if await auth_repo.get_beta_wave_by_key(body.key):
        raise HTTPException(
            status_code=409,
            detail="A wave with this key already exists",
        )
    sort_order = body.sort_order
    if sort_order is None:
        sort_order = await auth_repo.compute_next_beta_wave_sort_order()
    try:
        row = await auth_repo.create_beta_wave(
            body.key, body.label, body.description, sort_order
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    logger.info(
        "admin_create_beta_wave | admin_user_id={} wave_id={} wave_key={}",
        ctx.user_id,
        row.get("id"),
        row.get("key"),
    )
    return _beta_wave_row_to_item(row)


@router.patch("/beta-waves/{wave_id}")
async def patch_beta_wave_admin(
    request: Request,
    wave_id: UUID,
    body: WavePatchRequest,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    try:
        updated = await auth_repo.update_beta_wave(
            wave_id,
            label=body.label,
            description=body.description,
            sort_order=body.sort_order,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if updated is None:
        raise HTTPException(status_code=404, detail="Wave not found")
    logger.info(
        "admin_patch_beta_wave | admin_user_id={} wave_id={}",
        ctx.user_id,
        wave_id,
    )
    return _beta_wave_row_to_item(updated)


@router.delete("/beta-waves/{wave_id}", status_code=204)
async def delete_beta_wave_admin(
    request: Request,
    wave_id: UUID,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    result = await auth_repo.delete_beta_wave_if_unused(wave_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Wave not found")
    if result == "in_use":
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete wave: still referenced by waitlist submissions, "
                "invitation codes, or user profiles"
            ),
        )
    logger.info(
        "admin_delete_beta_wave | admin_user_id={} wave_id={}",
        ctx.user_id,
        wave_id,
    )


@router.get("/waitlist-submissions")
async def list_waitlist_submissions_admin(
    request: Request,
    ctx: AuthContext = Depends(require_admin_managed_auth),
    q: str | None = None,
    status: str | None = Query(
        None,
        description="Comma-separated status values (e.g. PENDING_REVIEW,INVITED)",
    ),
    beta_wave_id: UUID | None = Query(None, alias="betaWaveId"),
    heard_about: str | None = Query(None, alias="heardAbout"),
    invited: bool | None = Query(None),
    sort: str = Query("last_submitted_at_desc"),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
):
    wl_repo: SupabaseBetaWaitlistRepository = request.app.state.beta_waitlist_repository
    offset = _decode_waitlist_cursor(cursor)
    sort_key = sort if sort in WAITLIST_ADMIN_SORTS else "last_submitted_at_desc"
    statuses_list: list[str] | None = None
    if status and status.strip():
        statuses_list = [s.strip() for s in status.split(",") if s.strip()]
        invalid = [s for s in statuses_list if s not in WAITLIST_STATUSES]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status value(s): {', '.join(invalid)}",
            )
    rows, has_more = await wl_repo.list_for_admin(
        q=q,
        statuses=statuses_list,
        beta_wave_id=str(beta_wave_id) if beta_wave_id else None,
        heard_about=heard_about,
        invited=invited,
        sort=sort_key,
        limit=limit,
        offset=offset,
    )
    items = [_waitlist_row_to_item(r) for r in rows]
    next_cursor = (
        _encode_waitlist_cursor(offset + len(items)) if has_more else None
    )
    logger.info(
        "admin_list_waitlist_submissions | admin_user_id={} count={}",
        ctx.user_id,
        len(items),
    )
    return {"items": items, "nextCursor": next_cursor}


class WaitlistPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    admin_notes: str | None = Field(None, alias="adminNotes")
    beta_wave_id: UUID | None = Field(None, alias="betaWaveId")
    status: str | None = None
    reviewed_at: datetime | None = Field(None, alias="reviewedAt")


@router.patch("/waitlist-submissions/{submission_id}")
async def patch_waitlist_submission_admin(
    request: Request,
    submission_id: UUID,
    body: WaitlistPatchRequest,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    wl_repo: SupabaseBetaWaitlistRepository = request.app.state.beta_waitlist_repository
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    updates: dict = {}
    if "admin_notes" in body.model_fields_set:
        updates["admin_notes"] = body.admin_notes
    if "beta_wave_id" in body.model_fields_set:
        if body.beta_wave_id is not None:
            wave = await auth_repo.get_beta_wave_by_id(body.beta_wave_id)
            if wave is None:
                raise HTTPException(
                    status_code=400,
                    detail="betaWaveId does not reference an existing beta wave",
                )
        updates["beta_wave_id"] = body.beta_wave_id
    if "status" in body.model_fields_set:
        if body.status is not None and body.status not in WAITLIST_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"status must be one of {sorted(WAITLIST_STATUSES)}",
            )
        updates["status"] = body.status
    if "reviewed_at" in body.model_fields_set:
        updates["reviewed_at"] = (
            body.reviewed_at.isoformat() if body.reviewed_at is not None else None
        )
    updated = await wl_repo.patch_submission_admin(submission_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Waitlist submission not found")
    logger.info(
        "admin_patch_waitlist_submission | admin_user_id={} submission_id={}",
        ctx.user_id,
        submission_id,
    )
    return _waitlist_row_to_item(updated)


class IssueFromWaitlistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    user_type: str = Field(alias="userType")
    issued_to: str | None = Field(None, alias="issuedTo")
    platform_issued_on: str | None = Field(None, alias="platformIssuedOn")
    cohort_id: UUID | None = Field(None, alias="cohortId")
    beta_wave_id: UUID | None = Field(None, alias="betaWaveId")


@router.post("/waitlist-submissions/{submission_id}/issue-invitation")
async def issue_invitation_from_waitlist_admin(
    request: Request,
    submission_id: UUID,
    body: IssueFromWaitlistRequest,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    if body.user_type not in USER_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"userType must be one of {USER_TYPES}, got {body.user_type!r}",
        )
    wl_repo: SupabaseBetaWaitlistRepository = request.app.state.beta_waitlist_repository
    auth_repo: SupabaseAuthRepository = request.app.state.supabase_auth_repository
    row = await wl_repo.get_by_id(submission_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Waitlist submission not found")

    issued_to = (
        body.issued_to.strip()
        if body.issued_to and body.issued_to.strip()
        else (row.get("email") or "").strip()
    )
    if not issued_to:
        raise HTTPException(
            status_code=400,
            detail="issuedTo or waitlist email is required to issue an invitation",
        )

    cohort_id_str: str | None = None
    if body.cohort_id is not None:
        cohort = await auth_repo.get_cohort_by_id(body.cohort_id)
        if cohort is None:
            raise HTTPException(
                status_code=400,
                detail="cohortId does not reference an existing cohort",
            )
        cohort_id_str = str(body.cohort_id)

    beta_wave_id_str: str | None = None
    if body.beta_wave_id is not None:
        wave = await auth_repo.get_beta_wave_by_id(body.beta_wave_id)
        if wave is None:
            raise HTTPException(
                status_code=400,
                detail="betaWaveId does not reference an existing beta wave",
            )
        beta_wave_id_str = str(body.beta_wave_id)

    cur_inv = row.get("invitation_code_id")
    if cur_inv:
        cur_s = str(cur_inv)
        inv_for_email = await auth_repo.get_invitation_by_issued_to(issued_to)
        if inv_for_email is None or str(inv_for_email["id"]) != cur_s:
            raise HTTPException(
                status_code=409,
                detail="Waitlist submission already linked to an invitation",
            )
        ex = dict(inv_for_email)
        if ex.get("beta_wave_id"):
            w = await auth_repo.get_beta_wave_by_id(ex["beta_wave_id"])
            if w:
                ex["beta_wave_key"] = w.get("key")
        logger.info(
            "admin_issue_waitlist_invite_idempotent | admin_user_id={} submission_id={}",
            ctx.user_id,
            submission_id,
        )
        return {
            "invitation": _issue_response_body(ex),
            "waitlist": _waitlist_row_to_item(row),
        }

    existing = await auth_repo.get_invitation_by_issued_to(issued_to)
    if existing is not None:
        inv_id = str(existing["id"])
        updated = await wl_repo.link_invitation_to_submission(
            submission_id,
            inv_id,
            beta_wave_id=beta_wave_id_str if beta_wave_id_str else None,
        )
        ex = dict(existing)
        if ex.get("beta_wave_id"):
            w = await auth_repo.get_beta_wave_by_id(ex["beta_wave_id"])
            if w:
                ex["beta_wave_key"] = w.get("key")
        logger.info(
            "admin_issue_waitlist_invite_linked_existing | admin_user_id={} submission_id={}",
            ctx.user_id,
            submission_id,
        )
        return {
            "invitation": _issue_response_body(ex),
            "waitlist": _waitlist_row_to_item(updated) if updated else {},
        }

    code = await auth_repo.generate_invitation_code()
    inv_row = await auth_repo.create_invitation_code(
        code=code,
        user_type=body.user_type,
        issued_to=issued_to,
        platform_issued_on=body.platform_issued_on,
        cohort_id=cohort_id_str,
        beta_wave_id=beta_wave_id_str,
    )
    updated = await wl_repo.link_invitation_to_submission(
        submission_id,
        str(inv_row["id"]),
        beta_wave_id=beta_wave_id_str if beta_wave_id_str else None,
    )
    if beta_wave_id_str:
        w = await auth_repo.get_beta_wave_by_id(beta_wave_id_str)
        if w:
            inv_row = {**inv_row, "beta_wave_key": w.get("key")}
    logger.info(
        "admin_issue_waitlist_invite_created | admin_user_id={} submission_id={}",
        ctx.user_id,
        submission_id,
    )
    return {
        "invitation": _issue_response_body(inv_row),
        "waitlist": _waitlist_row_to_item(updated) if updated else {},
    }


@router.get("/usage-providers")
async def list_usage_providers_admin(
    request: Request,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    """Catalog rows for usage_records.provider labels (YAML-seeded)."""
    client = getattr(request.app.state, "supabase_client", None)
    if client is None:
        raise HTTPException(status_code=501, detail="Supabase client not configured")
    logger.info("admin_list_usage_providers | admin_user_id={}", ctx.user_id)
    try:
        r = await client.table("usage_provider_definitions").select("*").order("provider_id").execute()
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
async def list_recent_runs_admin(
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
    runs = await run_repo.list_recent_job_runs(
        limit=limit,
        offset=offset,
        from_iso=from_ts,
        to_iso=to_ts,
        owner_user_ids=owner_filter,
    )
    rate_rows = await _load_rate_card_rows(request)
    items = []
    for jr in runs:
        uid = jr.owner_user_id
        counts = await run_repo.count_run_structure_for_job_run(jr.id, uid)
        usage_rows = await run_repo.list_usage_records_for_job_run(jr.id, uid)
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
async def list_user_runs_admin(
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
    runs = await run_repo.list_job_runs_by_owner(
        uid,
        limit=limit,
        offset=offset,
        from_iso=from_ts,
        to_iso=to_ts,
    )
    rate_rows = await _load_rate_card_rows(request)
    items = []
    for jr in runs:
        counts = await run_repo.count_run_structure_for_job_run(jr.id, uid)
        usage_rows = await run_repo.list_usage_records_for_job_run(jr.id, uid)
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
async def get_user_run_detail_admin(
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
    jr = await run_repo.get_job_run(jrid, uid)
    if jr is None:
        raise HTTPException(status_code=404, detail="Job run not found for this user")
    counts = await run_repo.count_run_structure_for_job_run(jrid, uid)
    usage_rows = await run_repo.list_usage_records_for_job_run(jrid, uid)
    stages = await run_repo.list_stage_runs_for_job_run(jrid, uid)
    pipelines = await run_repo.list_pipeline_run_executions_for_job_run(jrid, uid)
    steps = await run_repo.list_step_runs_for_job_run(jrid, uid)
    rate_rows = await _load_rate_card_rows(request)

    # Look up stage definitions for pipeline_run_mode
    stage_run_mode_map: dict[str, str] = {}
    if jr.job_id:
        client = getattr(request.app.state, "supabase_client", None)
        if client:
            try:
                r = await client.table("stage_definitions").select(
                    "id,pipeline_run_mode"
                ).eq("owner_user_id", uid).execute()
                for row in r.data or []:
                    stage_run_mode_map[row["id"]] = row.get("pipeline_run_mode", "parallel")
            except Exception as e:
                logger.warning("admin_run_detail_stage_mode_lookup_failed | error={}", e)

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
        "stageRuns": [_stage_run_admin_dict(s, stage_run_mode_map) for s in stages],
        "pipelineRunExecutions": [_pipeline_run_admin_dict(p) for p in pipelines],
        "stepRuns": [_step_run_admin_dict(s) for s in steps],
    }


# --- Resource limits (Postgres app_limits) ---


@router.get("/limits/global")
async def get_limits_global_admin(
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
async def put_limits_global_admin(
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
async def get_limits_new_user_defaults_admin(
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
async def put_limits_new_user_defaults_admin(
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
async def get_user_limits_detail_admin(
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
    n_jobs = len(await job_repo.list_by_owner(uid)) if job_repo else 0
    n_triggers = len(await trigger_repo.list_by_owner(uid)) if trigger_repo else 0

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    runs_day = 0
    runs_month = 0
    if run_repo is not None and hasattr(run_repo, "count_job_runs_owner_since_utc"):
        runs_day = await run_repo.count_job_runs_owner_since_utc(uid, day_start.isoformat())
        runs_month = await run_repo.count_job_runs_owner_since_utc(uid, month_start.isoformat())

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
async def put_user_limits_admin(
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
