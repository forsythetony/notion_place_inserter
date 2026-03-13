"""Locations API routes."""

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


class LocationRequest(BaseModel):
    """Request body for POST /locations."""

    keywords: str


@router.post("/locations")
def create_location(request: Request, body: LocationRequest, _: None = Depends(require_auth)):
    """
    Create a place entry in the Places to Visit database.
    Runs pipeline (query rewrite + Google Places + property resolution).
    Keywords must be non-empty. For random test entries, use POST /test/randomLocation.
    When async is enabled, returns immediately with job_id; pipeline runs in background.
    """
    if not body.keywords.strip():
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
        places_service = request.app.state.places_service
        return places_service.create_place_from_query(body.keywords)

    queue_repo = getattr(request.app.state, "supabase_queue_repository", None)
    run_repo = getattr(request.app.state, "supabase_run_repository", None)
    if queue_repo is None or run_repo is None:
        logger.warning("locations_enqueue_skipped | supabase_repos_unavailable")
        raise HTTPException(
            status_code=503,
            detail="Unable to enqueue request",
        )

    job_id = _job_id()
    run_id = str(uuid.uuid4())
    recipient_whatsapp = None

    try:
        run_repo.create_job(job_id=job_id, keywords=body.keywords, status="queued")
        run_repo.create_run(job_id=job_id, run_id=run_id, status="pending")
        payload = {
            "job_id": job_id,
            "run_id": run_id,
            "keywords": body.keywords,
        }
        if recipient_whatsapp is not None:
            payload["recipient_whatsapp"] = recipient_whatsapp
        queue_repo.send(payload, delay_seconds=0)
        logger.info(
            "locations_enqueued | job_id={} run_id={} keywords_preview={}",
            job_id,
            run_id,
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
