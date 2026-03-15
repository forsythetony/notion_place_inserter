"""Unit tests for SchemaCache."""

import time
from unittest.mock import MagicMock

import pytest

from app.models.schema import DatabaseSchema, parse_schema
from app.services.schema_cache import SchemaCache


def test_parse_schema():
    """parse_schema produces typed PropertySchema with select options."""
    raw = {
        "Title": {"type": "title"},
        "Type": {
            "type": "select",
            "select": {
                "options": [
                    {"id": "a", "name": "Park", "color": "green"},
                    {"id": "b", "name": "Museum", "color": "blue"},
                ]
            },
        },
    }
    schema = parse_schema("Test DB", "ds-123", raw)
    assert isinstance(schema, DatabaseSchema)
    assert schema.db_name == "Test DB"
    assert schema.data_source_id == "ds-123"
    assert schema.properties["Title"].type == "title"
    assert schema.properties["Type"].type == "select"
    assert len(schema.properties["Type"].options or []) == 2
    assert schema.properties["Type"].options[0].name == "Park"


def test_schema_cache_ttl_refresh():
    """Cache returns cached entry within TTL, fetches fresh after expiry."""
    mock_client = MagicMock()
    mock_client.databases.retrieve.return_value = {
        "title": [{"plain_text": "Places"}],
        "data_sources": [{"id": "ds-1", "name": "Places to Visit"}],
    }
    mock_client.data_sources.retrieve.return_value = {
        "properties": {"Name": {"type": "title"}},
    }
    cache = SchemaCache(mock_client, database_ids=["db-1"], ttl_seconds=0.1)
    entry1 = cache.get("Places to Visit")
    entry2 = cache.get("Places to Visit")
    assert entry1 is entry2
    assert mock_client.databases.retrieve.call_count == 1
    time.sleep(0.15)
    entry3 = cache.get("Places to Visit")
    assert mock_client.databases.retrieve.call_count == 2


def test_schema_cache_invalidate():
    """invalidate clears entry so next get fetches fresh."""
    mock_client = MagicMock()
    mock_client.databases.retrieve.return_value = {
        "title": [{"plain_text": "Places"}],
        "data_sources": [{"id": "ds-1", "name": "Places to Visit"}],
    }
    mock_client.data_sources.retrieve.return_value = {
        "properties": {"Name": {"type": "title"}},
    }
    cache = SchemaCache(mock_client, database_ids=["db-1"], ttl_seconds=300)
    cache.get("Places to Visit")
    cache.invalidate("Places to Visit")
    cache.get("Places to Visit")
    assert mock_client.databases.retrieve.call_count == 2


def test_schema_cache_supports_configured_data_source_id():
    """Configured IDs can be direct data source IDs (database lookup may 404)."""
    mock_client = MagicMock()
    mock_client.databases.retrieve.side_effect = Exception("404")
    mock_client.data_sources.retrieve.return_value = {
        "title": [{"plain_text": "Places to Visit"}],
        "properties": {"Name": {"type": "title"}},
    }

    cache = SchemaCache(mock_client, database_ids=["ds-123"], ttl_seconds=300)
    entry = cache.get("Places to Visit")

    assert entry.data_source_id == "ds-123"
    assert "Name" in entry.properties


def test_schema_cache_skips_unusable_ids_and_uses_next():
    """One bad configured ID should not fail resolution if a later ID works."""
    mock_client = MagicMock()

    def retrieve_db(database_id: str):
        if database_id == "bad-id":
            raise Exception("404")
        return {
            "title": [{"plain_text": "Places"}],
            "data_sources": [{"id": "ds-good", "name": "Places to Visit"}],
        }

    mock_client.databases.retrieve.side_effect = retrieve_db
    mock_client.data_sources.retrieve.return_value = {
        "properties": {"Name": {"type": "title"}},
    }

    cache = SchemaCache(mock_client, database_ids=["bad-id", "db-good"], ttl_seconds=300)
    entry = cache.get("Places to Visit")

    assert entry.data_source_id == "ds-good"
    assert "Name" in entry.properties
