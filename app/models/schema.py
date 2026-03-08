"""Typed schema models for Notion database properties."""

import time
from dataclasses import dataclass


@dataclass
class SelectOption:
    """A single option in a Notion select or multi_select property."""

    id: str
    name: str
    color: str


@dataclass
class PropertySchema:
    """Schema for a single Notion property."""

    name: str
    type: str  # "title", "select", "rich_text", "url", etc.
    options: list[SelectOption] | None = None  # for select / multi_select


@dataclass
class DatabaseSchema:
    """Parsed schema for a Notion database."""

    db_name: str
    data_source_id: str
    properties: dict[str, PropertySchema]
    fetched_at: float


def parse_schema(
    db_name: str, data_source_id: str, raw_properties: dict
) -> DatabaseSchema:
    """Parse raw Notion API properties into a typed DatabaseSchema."""
    props: dict[str, PropertySchema] = {}
    for name, raw in raw_properties.items():
        prop_type = raw.get("type", "unknown")
        options = None
        if prop_type in ("select", "multi_select"):
            raw_opts = raw.get(prop_type, {}).get("options", [])
            options = [
                SelectOption(
                    id=o.get("id", ""),
                    name=o.get("name", ""),
                    color=o.get("color", ""),
                )
                for o in raw_opts
            ]
        props[name] = PropertySchema(name=name, type=prop_type, options=options)
    return DatabaseSchema(
        db_name=db_name,
        data_source_id=data_source_id,
        properties=props,
        fetched_at=time.monotonic(),
    )
