"""Convert execution context property map to Notion API payload."""

from __future__ import annotations

from typing import Any

from app.models.schema import PropertySchema, SelectOption
from app.pipeline_lib.steps.notion_format import format_value_for_notion


def build_notion_properties_payload(
    ctx_properties: dict[str, Any],
    active_schema: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert ctx.properties (schema_property_id -> raw value) to Notion API format.
    Uses active_schema to resolve property type, external_property_id, and options.
    """
    result: dict[str, Any] = {}
    props = active_schema.get("properties") or []
    prop_by_id = {p.get("id"): p for p in props if isinstance(p, dict) and p.get("id")}

    for schema_property_id, raw_value in ctx_properties.items():
        prop_def = prop_by_id.get(schema_property_id)
        if not prop_def:
            continue
        prop_type = prop_def.get("property_type", "rich_text")
        name = prop_def.get("name", schema_property_id)
        external_id = prop_def.get("external_property_id") or name
        raw_opts = prop_def.get("options") or []
        options = [
            SelectOption(
                id=o.get("id", ""),
                name=o.get("name", str(o)),
                color=o.get("color", ""),
            )
            for o in raw_opts
            if isinstance(o, dict)
        ]
        schema = PropertySchema(name=name, type=prop_type, options=options or None)
        # format_value_for_notion expects comma-separated string for multi_select
        if prop_type == "multi_select" and isinstance(raw_value, list):
            raw_value = ", ".join(str(v) for v in raw_value)
        formatted = format_value_for_notion(raw_value, schema)
        if formatted is not None:
            result[external_id] = formatted
    return result
