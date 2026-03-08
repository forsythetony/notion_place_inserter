"""Reusable steps for formatting values as Notion API property formats."""

from app.models.schema import PropertySchema
from app.pipeline_lib.context import PipelineRunContext
from app.pipeline_lib.core import PipelineStep
from app.pipeline_lib.logging import log_step


class FormatAsNotionTitle(PipelineStep):
    """Format current value as Notion title property. Writes to context if prop_name given."""

    def __init__(self, prop_name: str | None = None):
        self._prop_name = prop_name

    @property
    def step_id(self) -> str:
        return "format_as_notion_title"

    def execute(
        self, context: PipelineRunContext, current_value: object
    ) -> object:
        from app.models.schema import PropertySchema

        with log_step(
            context.run_id,
            context.get("_global_pipeline_id", ""),
            context.get("_current_stage_id", ""),
            context.get("_current_pipeline_id", ""),
            self.step_id,
            step_name=self.name,
            step_description=self.description or None,
            property_name=self._prop_name,
            property_type="title",
        ):
            schema = PropertySchema(name=self._prop_name or "Title", type="title", options=None)
            formatted = format_value_for_notion(current_value, schema)
            if formatted is not None and self._prop_name:
                context.set_property(self._prop_name, formatted)
            return formatted


def format_value_for_notion(value: object, prop_schema: PropertySchema) -> dict | None:
    """
    Format a scalar or structured value into Notion API property format.
    Returns None if the value cannot be formatted for this property type.
    """
    prop_type = prop_schema.type
    str_val = str(value).strip() if value is not None else ""

    if prop_type == "title":
        if not str_val:
            return None
        return {
            "title": [
                {"type": "text", "text": {"content": str_val, "link": None}}
            ]
        }

    if prop_type == "rich_text":
        if not str_val:
            return None
        return {
            "rich_text": [
                {"type": "text", "text": {"content": str_val, "link": None}}
            ]
        }

    if prop_type == "url":
        if not str_val:
            return None
        if not str_val.startswith(("http://", "https://")):
            str_val = "https://" + str_val
        return {"url": str_val}

    if prop_type == "select":
        options = prop_schema.options or []
        if not str_val or not options:
            return None
        name_lower = str_val.lower()
        for opt in options:
            if opt.name.lower() == name_lower:
                return {"select": {"name": opt.name}}
        return {"select": {"name": str_val}}

    if prop_type == "multi_select":
        options = prop_schema.options or []
        if not str_val or not options:
            return None
        parts = [p.strip() for p in str_val.split(",") if p.strip()]
        names = []
        for part in parts:
            part_lower = part.lower()
            for opt in options:
                if opt.name.lower() == part_lower:
                    names.append({"name": opt.name})
                    break
            else:
                names.append({"name": part})
        return {"multi_select": names} if names else None

    if prop_type == "number":
        try:
            return {"number": float(value)}
        except (TypeError, ValueError):
            return None

    if prop_type == "checkbox":
        if isinstance(value, bool):
            return {"checkbox": value}
        return {"checkbox": str(value).lower() in ("true", "1", "yes")}

    if prop_type == "date":
        if not str_val:
            return None
        return {"date": {"start": str_val}}

    if prop_type == "email":
        if not str_val:
            return None
        return {"email": str_val}

    if prop_type == "phone_number":
        if not str_val:
            return None
        return {"phone_number": str_val}

    return None
