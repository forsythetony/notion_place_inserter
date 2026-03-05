"""Notion API service wrapper with schema caching."""

from pathlib import Path

from loguru import logger
from notion_client import Client

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _extract_title_from_rich_text(rich_text_array: list) -> str:
    """Extract plain text from Notion rich text array."""
    if not rich_text_array:
        return ""
    return "".join(
        block.get("plain_text", "") or block.get("text", {}).get("content", "")
        for block in rich_text_array
    )


class NotionService:
    """Wraps the Notion API client and caches database schemas by name."""

    # Database IDs to fetch on startup (from the two provided Notion URLs)
    DATABASE_IDS = [
        "544d5797-9344-4258-aed6-1f72e66b6927",  # Locations
        "1e2a5cd4-f107-490f-9b7a-4af865fd1beb",  # Places to Visit
    ]

    def __init__(self, api_key: str):
        self._client = Client(auth=api_key)
        self._schema_cache: dict[str, dict] = {}  # db_name -> {schema, data_source_id}
        self._initialized = False

    def initialize(self) -> None:
        """Pull database schemas from Notion and cache them by database name."""
        for db_id in self.DATABASE_IDS:
            try:
                logger.info("Fetching database {}", db_id)
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
                    self._schema_cache[ds_name] = {
                        "properties": ds_full.get("properties", {}),
                        "data_source_id": ds_id,
                    }
                    logger.info("Cached schema for database '{}'", ds_name)
            except Exception as e:
                logger.error("Failed to fetch database {}: {}", db_id, e)
                raise

        self._initialized = True

    def get_schema(self, db_name: str) -> dict:
        """Return the cached properties schema for the given database name."""
        if not self._initialized:
            raise RuntimeError("NotionService not initialized; call initialize() first")
        entry = self._schema_cache.get(db_name)
        if not entry:
            raise KeyError(f"Unknown database: {db_name}")
        return entry["properties"]

    def get_data_source_id(self, db_name: str) -> str:
        """Return the data source ID for the given database name."""
        if not self._initialized:
            raise RuntimeError("NotionService not initialized; call initialize() first")
        entry = self._schema_cache.get(db_name)
        if not entry:
            raise KeyError(f"Unknown database: {db_name}")
        return entry["data_source_id"]

    def create_page(self, data_source_id: str, properties: dict) -> dict:
        """Create a new page in the given data source with the provided properties."""
        return self._client.pages.create(
            parent={"data_source_id": data_source_id},
            properties=properties,
        )
