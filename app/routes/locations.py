"""Locations API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.dependencies import require_auth
from app.queue import enqueue_location_job

router = APIRouter()

# Max length guard to prevent abuse
KEYWORDS_MAX_LENGTH = 300


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

    job_queue = request.app.state.location_job_queue
    if job_queue is None:
        raise HTTPException(
            status_code=503,
            detail="Unable to enqueue request",
        )
    try:
        job_id, _run_id = enqueue_location_job(job_queue, body.keywords, recipient_whatsapp=None)
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Unable to enqueue request",
        )
    return {"status": "accepted", "job_id": job_id}
