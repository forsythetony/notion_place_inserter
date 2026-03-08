"""Lazy TTL cache for Notion database schemas."""

import time
from threading import Lock

from loguru import logger

from app.models.schema import DatabaseSchema, parse_schema


def _extract_title_from_rich_text(rich_text_array: list) -> str:
    """Extract plain text from Notion rich text array."""
    if not rich_text_array:
        return ""
    return "".join(
        block.get("plain_text", "") or block.get("text", {}).get("content", "")
        for block in rich_text_array
    )


class SchemaCache:
    """Lazy TTL cache for Notion database schemas.

    On every get(), the cache checks whether the entry is stale. If stale,
    it re-fetches from Notion. If not, it returns the cached copy.
    No background polling, no timers, no threads.
    """

    def __init__(self, notion_client, database_ids: list[str], ttl_seconds: float = 300):
        self._client = notion_client
        self._database_ids = database_ids
        self._ttl = ttl_seconds
        self._entries: dict[str, DatabaseSchema] = {}
        self._lock = Lock()

    def get(self, db_name: str) -> DatabaseSchema:
        """Return the schema for the given database name, refreshing if stale."""
        with self._lock:
            entry = self._entries.get(db_name)
            if entry and (time.monotonic() - entry.fetched_at) < self._ttl:
                return entry

        # Fetch outside the lock to avoid blocking concurrent readers
        fresh = self._fetch(db_name)

        with self._lock:
            self._entries[db_name] = fresh
        return fresh

    def invalidate(self, db_name: str | None = None) -> None:
        """Force a refresh on next access. None = invalidate all."""
        with self._lock:
            if db_name:
                self._entries.pop(db_name, None)
            else:
                self._entries.clear()

    def _fetch(self, db_name: str) -> DatabaseSchema:
        """Retrieve database schema from Notion API and parse into DatabaseSchema."""
        for db_id in self._database_ids:
            try:
                database = self._client.databases.retrieve(database_id=db_id)
                db_title = _extract_title_from_rich_text(
                    database.get("title", [])
                )
                data_sources = database.get("data_sources", [])

                for ds in data_sources:
                    ds_id = ds.get("id")
                    if not ds_id:
                        continue
                    ds_full = self._client.data_sources.retrieve(
                        data_source_id=ds_id
                    )
                    ds_name = ds.get("name") or db_title
                    if ds_name == db_name:
                        raw_props = ds_full.get("properties", {})
                        return parse_schema(db_name, ds_id, raw_props)
            except Exception as e:
                logger.error("Failed to fetch database {}: {}", db_id, e)
                raise

        raise KeyError(f"Unknown database: {db_name}")
