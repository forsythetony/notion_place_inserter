"""Notion API service wrapper with schema caching."""

import time
from io import BytesIO

from loguru import logger
from notion_client import Client
from notion_client.errors import APIResponseError

from app.models.schema import DatabaseSchema, PropertySchema
from app.pipeline_lib.table_format import format_table_log
from app.services.schema_cache import SchemaCache


class NotionService:
    """Wraps the Notion API client and caches database schemas by name."""

    # Database IDs to fetch on startup (from the two provided Notion URLs)
    DATABASE_IDS = [
        "544d5797-9344-4258-aed6-1f72e66b6927",  # Locations
        "9592d56b-899e-440e-9073-b2f0768669ad",  # Places to Visit
    ]

    def __init__(self, api_key: str, schema_ttl: float = 300, dry_run: bool = False):
        self._client = Client(auth=api_key)
        self._api_key = api_key
        self._dry_run = dry_run
        self._cache = SchemaCache(
            self._client, database_ids=self.DATABASE_IDS, ttl_seconds=schema_ttl
        )

    @staticmethod
    def _get_property_type(prop_value: dict) -> str:
        """Return the Notion property type key from a property value."""
        for key in (
            "title",
            "rich_text",
            "url",
            "select",
            "multi_select",
            "checkbox",
            "number",
            "date",
            "email",
            "phone_number",
            "relation",
        ):
            if key in prop_value:
                return key
        return "?"

    @staticmethod
    def _extract_property_preview_str(prop_value: dict) -> str:
        """Extract a compact string preview from a Notion API property value for logging."""
        if not prop_value:
            return ""
        if "title" in prop_value:
            blocks = prop_value["title"] or []
            return "".join(
                b.get("plain_text", "") or b.get("text", {}).get("content", "")
                for b in blocks
            )
        if "rich_text" in prop_value:
            blocks = prop_value["rich_text"] or []
            text = "".join(
                b.get("plain_text", "") or b.get("text", {}).get("content", "")
                for b in blocks
            )
            return text[:80] + ("..." if len(text) > 80 else "")
        if "url" in prop_value:
            return prop_value["url"] or ""
        if "select" in prop_value:
            sel = prop_value["select"]
            return sel.get("name", "") if sel else ""
        if "multi_select" in prop_value:
            items = prop_value["multi_select"] or []
            return ", ".join(i.get("name", "") for i in items)
        if "checkbox" in prop_value:
            return str(prop_value["checkbox"])
        if "number" in prop_value:
            val = prop_value["number"]
            return str(val) if val is not None else ""
        if "date" in prop_value:
            d = prop_value["date"]
            if not d:
                return ""
            start = d.get("start", "")
            end = d.get("end", "")
            return f"{start} → {end}" if end else start
        if "email" in prop_value:
            return prop_value["email"] or ""
        if "phone_number" in prop_value:
            return prop_value["phone_number"] or ""
        if "relation" in prop_value:
            rel_list = prop_value.get("relation") or []
            if not rel_list:
                return "—"
            urls = []
            for item in rel_list:
                page_id = item.get("id") if isinstance(item, dict) else None
                if page_id:
                    compact = str(page_id).replace("-", "")
                    urls.append(f"https://www.notion.so/{compact}")
            return " | ".join(urls) if urls else "—"
        return str(prop_value)[:60]

    @staticmethod
    def _extract_media_url(payload: dict | None) -> str | None:
        """Extract a URL from Notion icon/cover payloads when present."""
        if not isinstance(payload, dict):
            return None
        external = payload.get("external")
        if isinstance(external, dict):
            url = external.get("url")
            if isinstance(url, str) and url:
                return url
        file_obj = payload.get("file")
        if isinstance(file_obj, dict):
            url = file_obj.get("url")
            if isinstance(url, str) and url:
                return url
        file_upload = payload.get("file_upload")
        if isinstance(file_upload, dict):
            url = file_upload.get("url")
            if isinstance(url, str) and url:
                return url
        return None

    def _get_external_id_to_display_name_map(self, data_source_id: str) -> dict[str, str]:
        """
        Build external-property-id -> display-name map for a data source.
        Falls back to empty map on any retrieval/parsing error.
        """
        if not data_source_id:
            return {}
        try:
            data_source = self._client.data_sources.retrieve(data_source_id=data_source_id)
        except Exception:
            return {}

        raw_props = data_source.get("properties", {})
        if not isinstance(raw_props, dict):
            return {}

        mapping: dict[str, str] = {}
        for display_name, raw in raw_props.items():
            if not isinstance(raw, dict):
                continue
            external_id = raw.get("id")
            if isinstance(external_id, str) and external_id:
                mapping[external_id] = display_name
            if isinstance(display_name, str) and display_name:
                # Also map display-name keys to themselves for mixed-key payloads.
                mapping[display_name] = display_name
        return mapping

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

    @staticmethod
    def get_raw_schema_for_data_source(access_token: str, data_source_id: str) -> tuple[str, dict]:
        """
        Fetch raw properties for a data source using the given OAuth access token.
        Returns (data_source_id, raw_properties). Used for OAuth-connected targets.
        """
        client = Client(auth=access_token)
        ds = client.data_sources.retrieve(data_source_id=data_source_id)
        raw_props = ds.get("properties") or {}
        return data_source_id, raw_props

    @staticmethod
    def create_page_with_token(
        access_token: str,
        data_source_id: str,
        properties: dict,
        *,
        icon: dict | None = None,
        cover: dict | None = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Create a page using the given OAuth access token. Used for OAuth-connected targets.
        """
        client = Client(auth=access_token)
        payload = {
            "parent": {"data_source_id": data_source_id},
            "properties": properties,
        }
        if icon is not None:
            payload["icon"] = icon
        if cover is not None:
            payload["cover"] = cover
        if dry_run:
            return {"mode": "dry_run", **payload}
        return NotionService._create_page_with_retry(client, payload, icon=icon, cover=cover)

    @staticmethod
    def _create_page_with_retry(
        client: Client,
        payload: dict[str, object],
        *,
        icon: dict | None = None,
        cover: dict | None = None,
    ) -> dict:
        """Retry short Notion propagation race for file_upload payloads."""
        has_file_upload_payload = False
        for media_payload in (icon, cover):
            if not isinstance(media_payload, dict):
                continue
            file_upload = media_payload.get("file_upload")
            if isinstance(file_upload, dict) and file_upload.get("id"):
                has_file_upload_payload = True
                break

        retry_delays_seconds = (0.75, 1.5)
        for attempt in range(len(retry_delays_seconds) + 1):
            try:
                return client.pages.create(**payload)
            except APIResponseError as exc:
                message = str(exc)
                should_retry = (
                    has_file_upload_payload
                    and "Could not find file_upload with ID" in message
                    and attempt < len(retry_delays_seconds)
                )
                if not should_retry:
                    raise
                delay_seconds = retry_delays_seconds[attempt]
                logger.warning(
                    "notion_create_page_file_upload_not_ready_retry | attempt={} delay_seconds={} error={}",
                    attempt + 1,
                    delay_seconds,
                    message,
                )
                time.sleep(delay_seconds)
        raise RuntimeError("Unreachable create_page retry loop")

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
        access_token: str | None = None,
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
            upload_client = Client(auth=access_token) if access_token else self._client
            logger.info(
                "notion_file_upload_create_started | bytes_len={} filename={} content_type={}",
                len(image_bytes),
                filename,
                content_type,
            )
            created = upload_client.file_uploads.create(
                mode="single_part",
                filename=filename,
                content_type=content_type,
            )
            upload_id = created.get("id")
            if not upload_id:
                logger.warning("notion_file_upload_create_missing_id")
                return None

            logger.info("notion_file_upload_send_started | upload_id={}", upload_id)
            upload_client.file_uploads.send(
                upload_id,
                file=(filename, BytesIO(image_bytes), content_type),
            )

            initial_status = upload_client.file_uploads.retrieve(upload_id).get("status")
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
                    upload_client.file_uploads.complete(upload_id)
                except Exception as exc:
                    logger.warning(
                        "notion_file_upload_complete_exception | upload_id={} error={}",
                        upload_id,
                        str(exc),
                    )
                    # Handle race where upload transitions to "uploaded" before complete call.
                    status_after_exception = upload_client.file_uploads.retrieve(upload_id).get("status")
                    if status_after_exception == "uploaded":
                        logger.info("notion_file_upload_uploaded | upload_id={}", upload_id)
                        return {"type": "file_upload", "file_upload": {"id": upload_id}}
                    return None

            for _ in range(poll_max_attempts):
                status = upload_client.file_uploads.retrieve(upload_id)
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
        cover_url = self._extract_media_url(cover)
        icon_url = self._extract_media_url(icon)
        property_count = len(properties) if isinstance(properties, dict) else 0
        display_name_map = self._get_external_id_to_display_name_map(data_source_id)
        request_table = format_table_log(
            "notion_create_page_request",
            ["data_source_id", "dry_run", "property_count", "cover_url", "icon_url"],
            [[data_source_id, str(self._dry_run), str(property_count), cover_url or "—", icon_url or "—"]],
        )
        logger.debug("\n{}", request_table)
        if isinstance(properties, dict) and properties:
            prop_rows = [
                [
                    display_name_map.get(name, name),
                    name,
                    self._get_property_type(val),
                    self._extract_property_preview_str(val),
                ]
                for name, val in sorted(properties.items())
            ]
            props_table = format_table_log(
                "notion_create_page_properties",
                ["Display Name", "External ID", "Type", "Value"],
                prop_rows,
            )
            logger.debug("\n{}", props_table)
        payload: dict = {
            "parent": {"data_source_id": data_source_id},
            "properties": properties,
        }
        if icon is not None:
            payload["icon"] = icon
        if cover is not None:
            payload["cover"] = cover
        if self._dry_run:
            dry_run_table = format_table_log(
                "notion_create_page_skipped_dry_run",
                ["mode", "data_source_id", "property_count", "has_icon", "has_cover"],
                [["dry_run", data_source_id, str(property_count), str(icon is not None), str(cover is not None)]],
            )
            logger.info("\n{}", dry_run_table)
            return {
                "mode": "dry_run",
                "parent": payload["parent"],
                "properties": payload["properties"],
                **({"icon": icon} if icon is not None else {}),
                **({"cover": cover} if cover is not None else {}),
            }
        result = self._create_page_with_retry(self._client, payload, icon=icon, cover=cover)

        page_id = result.get("id", "") if isinstance(result, dict) else ""
        obj_type = result.get("object", "") if isinstance(result, dict) else ""
        success_table = format_table_log(
            "notion_create_page_success",
            ["data_source_id", "page_id", "object"],
            [[data_source_id, page_id, obj_type]],
        )
        logger.info("\n{}", success_table)
        return result
