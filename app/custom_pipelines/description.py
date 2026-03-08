"""Custom pipeline for Description: build fact pack, polish with Claude, format for Notion."""

from app.models.schema import PropertySchema
from app.pipeline_lib.context import ContextKeys, PipelineRunContext
from app.pipeline_lib.core import Pipeline, PipelineStep
from app.pipeline_lib.logging import log_step
from app.pipeline_lib.steps.notion_format import format_value_for_notion


def _build_fact_pack(place: dict) -> dict:
    """Extract structured facts from place for description generation."""
    primary = place.get("primaryType") or ""
    types = place.get("types") or []
    type_str = primary or (", ".join(types[:3]) if types else "")
    return {
        "name": place.get("displayName", ""),
        "address": place.get("formattedAddress", ""),
        "primaryType": primary,
        "types": type_str,
        "editorialSummary": place.get("editorialSummary"),
        "generativeSummary": place.get("generativeSummary"),
        "rating": place.get("rating"),
    }


def _deterministic_fallback(fact_pack: dict) -> str:
    """Produce a non-empty description when Claude is unavailable."""
    name = (fact_pack.get("name") or "").strip()
    addr = (fact_pack.get("address") or "").strip()
    editorial = (fact_pack.get("editorialSummary") or "").strip()
    generative = (fact_pack.get("generativeSummary") or "").strip()
    rating = fact_pack.get("rating")

    if editorial:
        base = editorial
    elif generative:
        base = generative
    else:
        parts = []
        if name and addr:
            parts.append(f"{name} at {addr}")
        elif name:
            parts.append(name)
        elif addr:
            parts.append(addr)
        base = ". ".join(parts) if parts else ""

    if rating is not None and base:
        base = f"{base} Rating: {rating}/5."
    elif rating is not None and not base:
        base = f"Rating: {rating}/5"
    return base.strip() if base else (name or "Place")


class BuildFactPackStep(PipelineStep):
    """Build structured fact pack from place data."""

    def __init__(self, prop_name: str):
        self._prop_name = prop_name

    @property
    def step_id(self) -> str:
        return "build_fact_pack"

    def execute(
        self, context: PipelineRunContext, current_value: object
    ) -> object:
        with log_step(
            context.run_id,
            context.get("_global_pipeline_id", ""),
            context.get("_current_stage_id", ""),
            context.get("_current_pipeline_id", ""),
            self.step_id,
            step_name=self.name,
            step_description=self.description or None,
            property_name=self._prop_name,
        ):
            place = context.get(ContextKeys.GOOGLE_PLACE)
            if not place:
                return None
            return _build_fact_pack(place)


class ClaudePolishDescriptionStep(PipelineStep):
    """Rewrite fact pack into a polished paragraph with Claude; fallback to deterministic template."""

    def __init__(self, prop_name: str):
        self._prop_name = prop_name

    @property
    def step_id(self) -> str:
        return "claude_polish_description"

    def execute(
        self, context: PipelineRunContext, current_value: object
    ) -> object:
        with log_step(
            context.run_id,
            context.get("_global_pipeline_id", ""),
            context.get("_current_stage_id", ""),
            context.get("_current_pipeline_id", ""),
            self.step_id,
            step_name=self.name,
            step_description=self.description or None,
            property_name=self._prop_name,
        ):
            fact_pack = current_value
            if fact_pack is None:
                return None
            if not isinstance(fact_pack, dict):
                return _deterministic_fallback({})

            claude = context.get("_claude_service")
            if claude:
                try:
                    polished = claude.polish_place_description(fact_pack)
                    if polished:
                        return polished
                except Exception:
                    pass

            return _deterministic_fallback(fact_pack)


class FormatDescriptionStep(PipelineStep):
    """Format as Notion rich_text."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def step_id(self) -> str:
        return "format_description"

    def execute(
        self, context: PipelineRunContext, current_value: object
    ) -> object:
        with log_step(
            context.run_id,
            context.get("_global_pipeline_id", ""),
            context.get("_current_stage_id", ""),
            context.get("_current_pipeline_id", ""),
            self.step_id,
            step_name=self.name,
            step_description=self.description or None,
            property_name=self._prop_name,
            property_type=self._prop_schema.type,
        ):
            formatted = format_value_for_notion(current_value, self._prop_schema)
            if formatted is not None:
                context.set_property(self._prop_name, formatted)
            return formatted


class DescriptionPipeline(Pipeline):
    """Resolve description from place data: fact pack -> Claude polish -> format."""

    def __init__(self, prop_name: str, prop_schema: PropertySchema):
        self._prop_name = prop_name
        self._prop_schema = prop_schema

    @property
    def pipeline_id(self) -> str:
        return f"description_{self._prop_name}"

    def steps(self) -> list[PipelineStep]:
        return [
            BuildFactPackStep(self._prop_name),
            ClaudePolishDescriptionStep(self._prop_name),
            FormatDescriptionStep(self._prop_name, self._prop_schema),
        ]
