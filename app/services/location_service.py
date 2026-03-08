"""Locations DB service: fetch, match, and create location pages with 30-minute caching."""

import os
import re
from typing import TYPE_CHECKING

from loguru import logger

from app.models.location import LocationCandidate, LocationNode, LocationResolution
from app.services.location_index_cache import LocationIndexCache
from app.services.notion_service import NotionService

if TYPE_CHECKING:
    from app.services.claude_service import ClaudeService


def _normalize_for_match(s: str) -> str:
    """Normalize string for matching: lowercase, collapse whitespace, strip."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.lower().strip())


def _score_match(candidate: LocationCandidate, node: LocationNode) -> tuple[float, str]:
    """
    Score match between candidate and node. Returns (score, matched_by).
    score 1.0: exact normalized name + same country (if both have)
    score 0.9: exact normalized name only
    score 0.0: no match
    """
    c_name = _normalize_for_match(candidate.display_name)
    n_name = _normalize_for_match(node.name)
    if c_name != n_name:
        return (0.0, "")
    if candidate.country and node.country:
        if _normalize_for_match(candidate.country) != _normalize_for_match(node.country):
            return (0.7, "normalized_name")  # name matches but country differs
    return (1.0, "exact_name")


class LocationService:
    """Wraps the Locations DB: fetch all locations, match or create, with 30-minute cache."""

    LOCATIONS_DB_NAME = "Locations"
    PARENT_PROPERTY = "Parent item"
    NAME_PROPERTY = "Name"
    TYPE_PROPERTY = "Type"
    COUNTRY_PROPERTY = "Country"

    def __init__(
        self,
        notion_service: NotionService,
        claude_service: "ClaudeService | None" = None,
        cache_ttl_seconds: float | None = None,
    ):
        self._notion = notion_service
        self._claude = claude_service
        ttl = cache_ttl_seconds
        if ttl is None:
            ttl = float(os.environ.get("LOCATIONS_CACHE_TTL_SECONDS", "1800"))
        min_confidence = float(os.environ.get("LOCATION_MATCH_MIN_CONFIDENCE", "0.85"))

        self._cache = LocationIndexCache(
            notion_client=notion_service.client,
            get_data_source_id_fn=notion_service.get_data_source_id,
            ttl_seconds=ttl,
        )
        self._min_confidence = min_confidence

    def get_all_locations(self, force_refresh: bool = False) -> list[LocationNode]:
        """Return all location nodes, using 30-minute cache unless force_refresh."""
        return self._cache.get(force_refresh=force_refresh)

    def find_best_match(self, candidate: LocationCandidate) -> tuple[LocationNode, float, str] | None:
        """
        Find best matching location. Returns (node, score, matched_by) or None.
        matched_by: "exact_name", "normalized_name"
        """
        nodes = self.get_all_locations()
        if not nodes:
            return None

        best: tuple[LocationNode, float, str] | None = None
        for node in nodes:
            score, matched_by = _score_match(candidate, node)
            if score >= self._min_confidence and (best is None or score > best[1]):
                best = (node, score, matched_by)
        return best

    def _claude_fallback_match(
        self,
        candidate: LocationCandidate,
        nodes: list[LocationNode],
        google_place: dict | None,
    ) -> LocationNode | None:
        """
        Use Claude constrained selection to pick one existing location from context.
        Returns the matching LocationNode or None when no clear match.
        """
        if not self._claude or not nodes:
            return None

        options = [n.name for n in nodes]
        candidate_context: dict = {
            "display_name": candidate.display_name,
            "state_or_region": candidate.state_or_region,
            "country": candidate.country,
        }
        if google_place:
            candidate_context["formattedAddress"] = google_place.get("formattedAddress")
            candidate_context["displayName"] = google_place.get("displayName")
            if google_place.get("addressComponents"):
                candidate_context["addressComponents"] = google_place["addressComponents"]

        selected = self._claude.choose_option_from_context(
            field_name="Location",
            options=options,
            candidate_context=candidate_context,
        )
        if not selected:
            return None

        for node in nodes:
            if node.name == selected:
                return node
        return None

    def create_location(
        self, candidate: LocationCandidate, parent: LocationNode | None = None
    ) -> LocationNode:
        """Create a new location page in the Locations DB and return the created node."""
        data_source_id = self._notion.get_data_source_id(self.LOCATIONS_DB_NAME)

        properties: dict = {
            self.NAME_PROPERTY: {
                "title": [{"type": "text", "text": {"content": candidate.display_name}}],
            },
        }

        if parent:
            properties[self.PARENT_PROPERTY] = {"relation": [{"id": parent.page_id}]}

        page = self._notion.create_page(data_source_id=data_source_id, properties=properties)

        node = LocationNode(
            page_id=page["id"],
            name=candidate.display_name,
            type_=None,
            country=candidate.country,
            parent_page_id=parent.page_id if parent else None,
        )
        self._cache.invalidate()
        return node

    def resolve_or_create(
        self,
        candidate: LocationCandidate,
        *,
        dry_run: bool = False,
        google_place: dict | None = None,
    ) -> LocationResolution | None:
        """
        Resolve to an existing location or create a new one.
        Tries deterministic exact match first, then Claude constrained selection,
        then create. When dry_run=True and no match, logs would-create and returns None.
        """
        nodes = self.get_all_locations()

        # 1. Deterministic exact match first
        match = self.find_best_match(candidate)
        if match:
            node, score, matched_by = match
            logger.bind(
                resolution_mode="matched",
                matched_page_id=node.page_id,
                matched_score=score,
                matched_by=matched_by,
                candidate_name=candidate.display_name,
            ).info("location_relation_matched")
            return LocationResolution(
                location_page_id=node.page_id,
                resolution_mode="matched",
                matched_score=score,
                matched_by=matched_by,
                parent_page_id=node.parent_page_id,
            )

        # 2. Claude constrained selection fallback
        claude_node = self._claude_fallback_match(candidate, nodes, google_place)
        if claude_node:
            logger.bind(
                resolution_mode="matched",
                matched_page_id=claude_node.page_id,
                matched_by="claude_constrained",
                candidate_name=candidate.display_name,
            ).info("location_relation_matched")
            return LocationResolution(
                location_page_id=claude_node.page_id,
                resolution_mode="matched",
                matched_score=None,
                matched_by="claude_constrained",
                parent_page_id=claude_node.parent_page_id,
            )

        # 3. No match: create or dry-run log
        parent_node: LocationNode | None = None
        if candidate.state_or_region:
            parent_candidate = LocationCandidate(
                display_name=candidate.state_or_region,
                country=candidate.country,
            )
            parent_match = self.find_best_match(parent_candidate)
            if parent_match:
                parent_node = parent_match[0]

        if dry_run:
            logger.bind(
                resolution_mode="would_create",
                candidate_name=candidate.display_name,
                parent_page_id=parent_node.page_id if parent_node else None,
            ).info("location_relation_would_create")
            return None

        created = self.create_location(candidate, parent=parent_node)
        logger.bind(
            resolution_mode="created",
            created_page_id=created.page_id,
            candidate_name=candidate.display_name,
            parent_page_id=created.parent_page_id,
        ).info("location_relation_created")

        return LocationResolution(
            location_page_id=created.page_id,
            resolution_mode="created",
            parent_page_id=created.parent_page_id,
        )
