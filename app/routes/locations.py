"""Trigger and locations API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel

from app.dependencies import require_auth

router = APIRouter()

# Max length guard to prevent abuse
KEYWORDS_MAX_LENGTH = 300


def _job_id() -> str:
    """Generate job_id in format loc_<hex>."""
    return f"loc_{uuid.uuid4().hex}"


def _normalize_trigger_path(path: str) -> str:
    """Ensure path has leading slash for trigger resolution."""
    p = (path or "").strip()
    return f"/{p}" if p and not p.startswith("/") else p or "/"


class TriggerLocationsRequest(BaseModel):
    """Request body for POST /triggers/{user_id}/locations."""

    keywords: str


@router.post("/triggers/{user_id}/{path:path}")
def invoke_trigger(
    request: Request,
    user_id: str,
    path: str,
    body: TriggerLocationsRequest,
    _: None = Depends(require_auth),
):
    """
    Invoke an HTTP trigger by user and path.
    User-scoped so Tony's /locations does not conflict with Patrick's.
    When async is enabled, returns immediately with job_id; pipeline runs in background.
    """
    if not (body.keywords or "").strip():
        raise HTTPException(
            status_code=400,
            detail="keywords is required and cannot be empty. Use POST /test/randomLocation for random test entries.",
        )
    if len(body.keywords) > KEYWORDS_MAX_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"keywords must be at most {KEYWORDS_MAX_LENGTH} characters",
        )

    async_enabled = getattr(request.app.state, "locations_async_enabled", False)
    if not async_enabled:
        job_execution_service = getattr(
            request.app.state, "job_execution_service", None
        )
        trigger_service_sync = getattr(request.app.state, "trigger_service", None)
        job_def_svc = getattr(request.app.state, "job_definition_service", None)
        if job_execution_service and trigger_service_sync and job_def_svc:
            normalized_path = _normalize_trigger_path(path)
            trigger = trigger_service_sync.resolve_by_path(normalized_path, user_id)
            if trigger:
                snapshot = job_def_svc.resolve_for_run(trigger.job_id, user_id)
                if snapshot:
                    run_id = str(uuid.uuid4())
                    trigger_payload = {"raw_input": body.keywords}
                    result = job_execution_service.execute_snapshot_run(
                        snapshot=snapshot.snapshot,
                        run_id=run_id,
                        job_id=f"sync_{run_id[:8]}",
                        trigger_payload=trigger_payload,
                        definition_snapshot_ref=snapshot.snapshot_ref,
                        owner_user_id=user_id,
                    )
                    return result
        places_service = getattr(request.app.state, "places_service", None)
        if places_service:
            return places_service.create_place_from_query(body.keywords)
        raise HTTPException(
            status_code=503,
            detail="Unable to run pipeline (sync mode)",
        )

    # Async path: enqueue for worker
    queue_repo = getattr(request.app.state, "supabase_queue_repository", None)
    run_repo = getattr(request.app.state, "supabase_run_repository", None)
    job_definition_service = getattr(
        request.app.state, "job_definition_service", None
    )
    trigger_service = getattr(request.app.state, "trigger_service", None)
    if queue_repo is None or run_repo is None:
        logger.warning("locations_enqueue_skipped | supabase_repos_unavailable")
        raise HTTPException(
            status_code=503,
            detail="Unable to enqueue request",
        )
    if job_definition_service is None:
        logger.warning(
            "locations_enqueue_skipped | job_definition_service_unavailable"
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to enqueue request",
        )
    if trigger_service is None:
        logger.warning("locations_enqueue_skipped | trigger_service_unavailable")
        raise HTTPException(
            status_code=503,
            detail="Unable to enqueue request",
        )

    normalized_path = _normalize_trigger_path(path)
    trigger = trigger_service.resolve_by_path(normalized_path, user_id)
    if trigger is None:
        logger.error(
            "trigger_enqueue_skipped | trigger_unavailable path={} user_id={}",
            normalized_path,
            user_id,
        )
        raise HTTPException(
            status_code=503,
            detail=f"Trigger not found for path '{normalized_path}' and user",
        )
    snapshot = job_definition_service.resolve_for_run(
        trigger.job_id, user_id
    )
    if snapshot is None:
        logger.error(
            "locations_enqueue_skipped | job_unavailable job_id={} owner={}",
            trigger.job_id,
            user_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Bootstrap job definition unavailable",
        )

    job_id = _job_id()
    run_id = str(uuid.uuid4())
    recipient_whatsapp = None
    job_definition_id = snapshot.snapshot["job"]["id"]
    target_data = snapshot.snapshot.get("target") or {}
    target_id = target_data.get("id", "")

    try:
        run_repo.create_job(
            job_id=job_id,
            keywords=body.keywords,
            status="queued",
            owner_user_id=user_id,
            run_id=run_id,
            job_definition_id=job_definition_id,
            trigger_id=trigger.id,
            target_id=target_id,
            definition_snapshot_ref=snapshot.snapshot_ref,
        )
        payload = {
            "job_id": job_id,
            "run_id": run_id,
            "keywords": body.keywords,
            "job_definition_id": job_definition_id,
            "job_slug": "notion_place_inserter",
            "definition_snapshot_ref": snapshot.snapshot_ref,
            "owner_user_id": user_id,
        }
        if recipient_whatsapp is not None:
            payload["recipient_whatsapp"] = recipient_whatsapp
        queue_repo.send(payload, delay_seconds=0)
        logger.info(
            "locations_enqueued | job_id={} run_id={} job_definition_id={} definition_snapshot_ref={} keywords_preview={}",
            job_id,
            run_id,
            job_definition_id,
            snapshot.snapshot_ref,
            body.keywords[:50] + "..." if len(body.keywords) > 50 else body.keywords,
        )
    except Exception:
        logger.exception(
            "locations_enqueue_failed | job_id={} run_id={}",
            job_id,
            run_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to enqueue request",
        )

    return {"status": "accepted", "job_id": job_id}
