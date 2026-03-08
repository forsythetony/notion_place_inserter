"""Job and event models for in-memory async processing."""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class LocationJob:
    """Job envelope for create_location_from_keywords pipeline."""

    job_id: str
    run_id: str
    keywords: str
    created_at: datetime
    attempt: int = 0


@dataclass
class PipelineSuccessEvent:
    """Event emitted when processing succeeds."""

    job_id: str
    run_id: str
    keywords: str
    result: dict


@dataclass
class PipelineFailureEvent:
    """Event emitted when processing fails."""

    job_id: str
    run_id: str
    keywords: str
    error: str | Exception
