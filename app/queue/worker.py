"""In-memory queue and worker loop for location processing."""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger

from app.queue.events import EventBus
from app.queue.models import LocationJob, PipelineFailureEvent, PipelineSuccessEvent

if TYPE_CHECKING:
    from app.services.places_service import PlacesService


def _job_id() -> str:
    """Generate job_id in format loc_<hex>."""
    return f"loc_{uuid.uuid4().hex}"


def create_location_queue() -> asyncio.Queue[LocationJob]:
    """Create a new in-memory queue for location jobs."""
    return asyncio.Queue()


def _run_pipeline_sync(places_service: "PlacesService", keywords: str) -> dict:
    """Run the synchronous pipeline (call from worker thread)."""
    return places_service.create_place_from_query(keywords)


async def run_worker_loop(
    job_queue: asyncio.Queue[LocationJob],
    places_service: "PlacesService",
    event_bus: EventBus,
) -> None:
    """
    Consume jobs from the queue and run the pipeline.
    Runs in a background task; use asyncio.create_task and cancel on shutdown.
    """
    loop = asyncio.get_event_loop()
    while True:
        try:
            job = await asyncio.wait_for(job_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue

        try:
            result = await loop.run_in_executor(
                None,
                lambda k=job.keywords: _run_pipeline_sync(places_service, k),
            )
            event_bus.publish_success(
                PipelineSuccessEvent(
                    job_id=job.job_id,
                    run_id=job.run_id,
                    keywords=job.keywords,
                    result=result,
                    recipient_whatsapp=job.recipient_whatsapp,
                )
            )
        except Exception as e:
            logger.exception("Pipeline failed for job {}", job.job_id)
            event_bus.publish_failure(
                PipelineFailureEvent(
                    job_id=job.job_id,
                    run_id=job.run_id,
                    keywords=job.keywords,
                    error=e,
                    recipient_whatsapp=job.recipient_whatsapp,
                )
            )


def enqueue_location_job(
    job_queue: asyncio.Queue[LocationJob],
    keywords: str,
    *,
    recipient_whatsapp: str | None = None,
) -> tuple[str, str]:
    """
    Enqueue a location job and return (job_id, run_id).
    Uses put_nowait since queue is unbounded.
    """
    job_id = _job_id()
    run_id = str(uuid.uuid4())
    job = LocationJob(
        job_id=job_id,
        run_id=run_id,
        keywords=keywords,
        created_at=datetime.now(timezone.utc),
        attempt=0,
        recipient_whatsapp=recipient_whatsapp,
    )
    job_queue.put_nowait(job)
    return job_id, run_id
