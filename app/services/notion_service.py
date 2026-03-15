"""Notion API service wrapper with schema caching."""

import time
from io import BytesIO

from loguru import logger
from notion_client import Client

from app.models.schema import DatabaseSchema, PropertySchema
from app.services.schema_cache import SchemaCache


class NotionService:
    """Wraps the Notion API client and caches database schemas by name."""

    # Database IDs to fetch on startup (from the two provided Notion URLs)
    DATABASE_IDS = [
        "544d5797-9344-4258-aed6-1f72e66b6927",  # Locations
        "1e2a5cd4-f107-490f-9b7a-4af865fd1beb",  # Places to Visit
    ]

    def __init__(self, api_key: str, schema_ttl: float = 300):
        self._client = Client(auth=api_key)
        self._api_key = api_key
        self._cache = SchemaCache(
            self._client, database_ids=self.DATABASE_IDS, ttl_seconds=schema_ttl
        )

    @property
    def client(self):
        """Underlying Notion API client for advanced operations (e.g. data_sources.query)."""
        return self._client

    def initialize(self) -> None:
        """Optionally warm the schema cache at startup."""
        for db_name in ("Places to Visit", "Locations"):
            try:
                self._cache.get(db_name)
            except KeyError:
                pass

    def get_schema(self, db_name: str) -> dict[str, PropertySchema]:
        """Return the cached properties schema for the given database name."""
        return self._cache.get(db_name).properties

    def get_database_schema(self, db_name: str) -> DatabaseSchema:
        """Return the full cached database schema."""
        return self._cache.get(db_name)

    def get_data_source_id(self, db_name: str) -> str:
        """Return the data source ID for the given database name."""
        return self._cache.get(db_name).data_source_id

    def get_raw_schema_for_sync(self, db_name: str) -> tuple[str, dict]:
        """
        Fetch raw properties for schema sync. Returns (data_source_id, raw_properties).
        Used by SchemaSyncService to build TargetSchemaSnapshot.
        """
        return self._cache.get_raw_for_sync(db_name)

    def invalidate_schema(self, db_name: str | None = None) -> None:
        """Force schema refresh on next access. None = invalidate all."""
        self._cache.invalidate(db_name)

    def upload_cover_from_bytes(
        self,
        image_bytes: bytes,
        *,
        filename: str = "cover.jpg",
        content_type: str = "image/jpeg",
        poll_interval: float = 1.0,
        poll_max_attempts: int = 30,
    ) -> dict | None:
        """
        Upload image bytes to Notion and return a cover payload for pages.create.
        Uses the File Upload API (create -> send -> complete -> poll for uploaded).
        Returns {"type": "file_upload", "file_upload": {"id": "..."}} or None on failure.
        """
        if not image_bytes:
            logger.warning("notion_file_upload_skipped_empty_bytes")
            return None
        try:
            logger.info(
                "notion_file_upload_create_started | bytes_len={} filename={} content_type={}",
                len(image_bytes),
                filename,
                content_type,
            )
            created = self._client.file_uploads.create(
                mode="single_part",
                filename=filename,
                content_type=content_type,
            )
            upload_id = created.get("id")
            if not upload_id:
                logger.warning("notion_file_upload_create_missing_id")
                return None

            logger.info("notion_file_upload_send_started | upload_id={}", upload_id)
            self._client.file_uploads.send(
                upload_id,
                file=(filename, BytesIO(image_bytes), content_type),
            )

            initial_status = self._client.file_uploads.retrieve(upload_id).get("status")
            logger.info(
                "notion_file_upload_status_after_send | upload_id={} status={}",
                upload_id,
                initial_status,
            )
            if initial_status == "uploaded":
                logger.info("notion_file_upload_uploaded | upload_id={}", upload_id)
                return {"type": "file_upload", "file_upload": {"id": upload_id}}
            if initial_status == "failed":
                logger.warning("notion_file_upload_failed | upload_id={}", upload_id)
                return None
            if initial_status == "pending":
                logger.info("notion_file_upload_complete_started | upload_id={}", upload_id)
                try:
                    self._client.file_uploads.complete(upload_id)
                except Exception as exc:
                    logger.warning(
                        "notion_file_upload_complete_exception | upload_id={} error={}",
                        upload_id,
                        str(exc),
                    )
                    # Handle race where upload transitions to "uploaded" before complete call.
                    status_after_exception = self._client.file_uploads.retrieve(upload_id).get("status")
                    if status_after_exception == "uploaded":
                        logger.info("notion_file_upload_uploaded | upload_id={}", upload_id)
                        return {"type": "file_upload", "file_upload": {"id": upload_id}}
                    return None

            for _ in range(poll_max_attempts):
                status = self._client.file_uploads.retrieve(upload_id)
                s = status.get("status")
                if s == "uploaded":
                    logger.info("notion_file_upload_uploaded | upload_id={}", upload_id)
                    return {"type": "file_upload", "file_upload": {"id": upload_id}}
                if s == "failed":
                    logger.warning("notion_file_upload_failed | upload_id={}", upload_id)
                    return None
                time.sleep(poll_interval)
            logger.warning(
                "notion_file_upload_poll_timeout | upload_id={} attempts={}",
                upload_id,
                poll_max_attempts,
            )
            return None
        except Exception as exc:
            logger.exception("notion_file_upload_exception | error={}", str(exc))
            return None

    def create_page(
        self,
        data_source_id: str,
        properties: dict,
        *,
        icon: dict | None = None,
        cover: dict | None = None,
    ) -> dict:
        """Create a new page in the given data source with the provided properties.
        Optionally include top-level icon and cover (Notion page metadata, not properties).
        """
        print(f"Creating page in data source {data_source_id}")
        payload: dict = {
            "parent": {"data_source_id": data_source_id},
            "properties": properties,
        }
        if icon is not None:
            payload["icon"] = icon
        if cover is not None:
            payload["cover"] = cover
        return self._client.pages.create(**payload)
