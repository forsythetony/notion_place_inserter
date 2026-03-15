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

    def _resolve_data_source_name(
        self,
        data_source: dict,
        fallback_db_title: str = "",
    ) -> str:
        """Best-effort data source display name extraction."""
        name = data_source.get("name", "")
        if isinstance(name, str) and name.strip():
            return name

        title = _extract_title_from_rich_text(data_source.get("title", []))
        if title.strip():
            return title

        parent = data_source.get("parent", {}) or {}
        parent_db_id = parent.get("database_id")
        if parent_db_id:
            try:
                parent_db = self._client.databases.retrieve(database_id=parent_db_id)
                parent_title = _extract_title_from_rich_text(parent_db.get("title", []))
                if parent_title.strip():
                    return parent_title
            except Exception:
                # Parent lookup is optional for name derivation.
                pass

        return fallback_db_title

    def _iter_data_source_schemas(self):
        """
        Yield tuples of (name, data_source_id, raw_properties) from configured IDs.

        Supports both legacy database IDs and newer data source IDs.
        """
        for configured_id in self._database_ids:
            # Path A: configured ID is a database ID.
            try:
                database = self._client.databases.retrieve(database_id=configured_id)
                db_title = _extract_title_from_rich_text(database.get("title", []))
                data_sources = database.get("data_sources", [])

                if data_sources:
                    for ds in data_sources:
                        ds_id = ds.get("id")
                        if not ds_id:
                            continue
                        try:
                            ds_full = self._client.data_sources.retrieve(data_source_id=ds_id)
                            ds_name = ds.get("name") or self._resolve_data_source_name(
                                ds_full, db_title
                            )
                            yield (ds_name, ds_id, ds_full.get("properties", {}))
                        except Exception:
                            logger.warning(
                                "Failed to fetch data source {} from database {}",
                                ds_id,
                                configured_id,
                            )
                            continue
                else:
                    # Legacy Notion DBs may expose properties directly on the database.
                    raw_props = database.get("properties", {})
                    if raw_props:
                        yield (db_title, configured_id, raw_props)
            except Exception:
                # Not a database ID (or not accessible); try as data source ID next.
                pass

            # Path B: configured ID is directly a data source ID.
            try:
                ds_full = self._client.data_sources.retrieve(data_source_id=configured_id)
                ds_name = self._resolve_data_source_name(ds_full, "")
                yield (ds_name, configured_id, ds_full.get("properties", {}))
            except Exception:
                # Not a data source ID (or not accessible); move on.
                continue

    def _fetch(self, db_name: str) -> DatabaseSchema:
        """Retrieve database schema from Notion API and parse into DatabaseSchema."""
        for ds_name, ds_id, raw_props in self._iter_data_source_schemas():
            if ds_name == db_name:
                return parse_schema(db_name, ds_id, raw_props)

        raise KeyError(f"Unknown database: {db_name}")

    def get_raw_for_sync(self, db_name: str) -> tuple[str, dict]:
        """
        Fetch raw properties and data_source_id for schema sync.
        Returns (data_source_id, raw_properties). Does not cache.
        """
        for ds_name, ds_id, raw_props in self._iter_data_source_schemas():
            if ds_name == db_name:
                return (ds_id, raw_props)

        raise KeyError(f"Unknown database: {db_name}")
