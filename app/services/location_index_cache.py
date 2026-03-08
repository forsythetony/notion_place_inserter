"""Lazy TTL cache for Locations DB page index."""

import time
from threading import Lock

from loguru import logger

from app.models.location import LocationNode


def _extract_title_from_rich_text(rich_text_array: list) -> str:
    """Extract plain text from Notion rich text array."""
    if not rich_text_array:
        return ""
    return "".join(
        block.get("plain_text", "") or block.get("text", {}).get("content", "")
        for block in rich_text_array
    )


def _parse_page_to_location_node(page: dict) -> LocationNode | None:
    """Parse a Notion page object into LocationNode. Returns None if page lacks required fields."""
    page_id = page.get("id")
    if not page_id:
        return None

    props = page.get("properties") or {}
    name = ""
    if "Name" in props and props["Name"].get("type") == "title":
        name = _extract_title_from_rich_text(props["Name"].get("title", []))
    if not name and "Title" in props and props["Title"].get("type") == "title":
        name = _extract_title_from_rich_text(props["Title"].get("title", []))

    type_val = None
    if "Type" in props and props["Type"].get("type") == "select":
        sel = props["Type"].get("select")
        if sel:
            type_val = sel.get("name")

    country = None
    if "Country" in props and props["Country"].get("type") == "select":
        sel = props["Country"].get("select")
        if sel:
            country = sel.get("name")

    parent_page_id = None
    if "Parent item" in props and props["Parent item"].get("type") == "relation":
        rel = props["Parent item"].get("relation") or []
        if rel and isinstance(rel, list):
            first = rel[0] if rel else None
            if first and isinstance(first, dict) and first.get("id"):
                parent_page_id = first["id"]
            elif first and isinstance(first, str):
                parent_page_id = first

    return LocationNode(
        page_id=page_id,
        name=name.strip() or "(unnamed)",
        type_=type_val,
        country=country,
        parent_page_id=parent_page_id,
    )


class LocationIndexCache:
    """Lazy TTL cache for normalized location nodes from the Locations DB.

    On every get(), the cache checks whether the entry is stale. If stale,
    it re-fetches from Notion. If not, it returns the cached copy.
    No background polling, no timers, no threads.
    """

    LOCATIONS_DB_NAME = "Locations"

    def __init__(self, notion_client, get_data_source_id_fn, ttl_seconds: float = 1800):
        self._client = notion_client
        self._get_data_source_id = get_data_source_id_fn
        self._ttl = ttl_seconds
        self._entries: list[LocationNode] = []
        self._fetched_at: float = 0.0
        self._lock = Lock()

    def get(self, force_refresh: bool = False) -> list[LocationNode]:
        """Return cached location nodes, refreshing if stale or force_refresh."""
        with self._lock:
            if not force_refresh and self._entries and (time.monotonic() - self._fetched_at) < self._ttl:
                return list(self._entries)

        # Fetch outside the lock to avoid blocking concurrent readers
        fresh = self._fetch()

        with self._lock:
            self._entries = fresh
            self._fetched_at = time.monotonic()
        return list(fresh)

    def invalidate(self) -> None:
        """Force a refresh on next access."""
        with self._lock:
            self._entries = []
            self._fetched_at = 0.0

    def _fetch(self) -> list[LocationNode]:
        """Retrieve all location pages from Notion and parse into LocationNode list."""
        data_source_id = self._get_data_source_id(self.LOCATIONS_DB_NAME)
        nodes: list[LocationNode] = []
        start_cursor = None

        filter_properties = ["Name", "Type", "Country", "Parent item"]

        while True:
            try:
                body: dict = {"page_size": 100}
                if start_cursor:
                    body["start_cursor"] = start_cursor

                resp = self._client.data_sources.query(
                    data_source_id=data_source_id,
                    filter_properties=filter_properties,
                    **body,
                )
            except Exception as e:
                logger.error("Failed to query Locations data source: {}", e)
                raise

            results = resp.get("results") or []
            for page in results:
                if page.get("object") != "page":
                    continue
                node = _parse_page_to_location_node(page)
                if node:
                    nodes.append(node)

            has_more = resp.get("has_more", False)
            start_cursor = resp.get("next_cursor")
            if not has_more or not start_cursor:
                break

        return nodes
