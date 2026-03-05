"""Location service for generating and creating place entries in Notion."""

import random
import uuid

from loguru import logger

from app.services.notion_service import NotionService

PLACES_DB_NAME = "Places to Visit"

# Property types we skip (computed, auto, or complex)
SKIP_TYPES = {"relation", "formula", "created_time", "place", "rollup"}


def _build_property_value(prop_name: str, prop_schema: dict) -> dict | None:
    """Build a Notion API property value for a random entry based on schema."""
    prop_type = prop_schema.get("type")
    if prop_type in SKIP_TYPES:
        return None

    if prop_type == "title":
        short_id = str(uuid.uuid4())[:8]
        return {"title": [{"type": "text", "text": {"content": f"Random Place {short_id}", "link": None}}]}

    if prop_type == "rich_text":
        return {"rich_text": [{"type": "text", "text": {"content": "Auto-generated test entry", "link": None}}]}

    if prop_type == "select":
        options = prop_schema.get("select", {}).get("options", [])
        if not options:
            return None
        opt = random.choice(options)
        return {"select": {"name": opt.get("name", opt.get("id", ""))}}

    if prop_type == "multi_select":
        options = prop_schema.get("multi_select", {}).get("options", [])
        if not options:
            return None
        k = min(random.randint(1, 3), len(options))
        chosen = random.sample(options, k)
        return {"multi_select": [{"name": o.get("name", o.get("id", ""))} for o in chosen]}

    if prop_type == "url":
        return {"url": "https://example.com/test"}

    if prop_type == "checkbox":
        return {"checkbox": random.choice([True, False])}

    if prop_type == "number":
        return {"number": random.randint(1, 100)}

    if prop_type == "date":
        from datetime import date
        d = date.today()
        return {"date": {"start": d.isoformat()}}

    if prop_type == "email":
        return {"email": "test@example.com"}

    if prop_type == "phone_number":
        return {"phone_number": "+15551234567"}

    return None


class LocationService:
    """Wraps functionality for creating new locations/places using NotionService."""

    def __init__(self, notion_service: NotionService):
        self._notion = notion_service

    def generate_random_entry(self, db_name: str) -> dict:
        """Generate a random property payload from the cached schema for the given DB."""
        schema = self._notion.get_schema(db_name)
        properties: dict = {}

        for prop_name, prop_schema in schema.items():
            value = _build_property_value(prop_name, prop_schema)
            if value is not None:
                properties[prop_name] = value

        return properties

    def create_location(self, entry: dict) -> dict:
        """Create a new place entry in the Places to Visit database."""
        data_source_id = self._notion.get_data_source_id(PLACES_DB_NAME)
        return self._notion.create_page(data_source_id=data_source_id, properties=entry)
