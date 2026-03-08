"""Domain models for Locations DB and relation resolution."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class LocationNode:
    """Normalized location record from the Locations DB."""

    page_id: str
    name: str
    type_: str | None  # "City", "State", etc.
    country: str | None
    parent_page_id: str | None = None


@dataclass
class LocationCandidate:
    """Candidate location extracted from place/query context for matching or creation."""

    display_name: str
    state_or_region: str | None = None
    country: str | None = None
    google_place_id: str | None = None


@dataclass
class LocationResolution:
    """Result of resolve_or_create: matched or created location with metadata."""

    location_page_id: str
    resolution_mode: Literal["matched", "created"]
    matched_score: float | None = None
    matched_by: str | None = None  # e.g. "exact_name", "normalized_name", "case_insensitive"
    parent_page_id: str | None = None
