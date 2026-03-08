"""Places service for generating and creating place entries in Notion."""

import random
import uuid

from app.app_global_pipelines import get_global_pipeline
from app.models.schema import PropertySchema
from app.pipeline_lib.context import ContextKeys, PipelineRunContext
from app.pipeline_lib.logging import log_pipeline_request
from app.services.dry_run_renderer import render_dry_run_table
from app.services.notion_service import NotionService

PLACES_DB_NAME = "Places to Visit"

# Property types we skip (computed, auto, or complex)
SKIP_TYPES = {"relation", "formula", "created_time", "place", "rollup"}


def _build_property_value(prop_name: str, prop_schema: PropertySchema) -> dict | None:
    """Build a Notion API property value for a random entry based on schema."""
    prop_type = prop_schema.type
    if prop_type in SKIP_TYPES:
        return None

    if prop_type == "title":
        short_id = str(uuid.uuid4())[:8]
        return {"title": [{"type": "text", "text": {"content": f"Random Place {short_id}", "link": None}}]}

    if prop_type == "rich_text":
        return {"rich_text": [{"type": "text", "text": {"content": "Auto-generated test entry", "link": None}}]}

    if prop_type == "select":
        options = prop_schema.options or []
        if not options:
            return None
        opt = random.choice(options)
        return {"select": {"name": opt.name or opt.id}}

    if prop_type == "multi_select":
        options = prop_schema.options or []
        if not options:
            return None
        k = min(random.randint(1, 3), len(options))
        chosen = random.sample(options, k)
        return {"multi_select": [{"name": o.name or o.id} for o in chosen]}

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


class PlacesService:
    """Wraps functionality for creating new places using NotionService."""

    def __init__(
        self,
        notion_service: NotionService,
        claude_service=None,
        google_places_service=None,
        location_service=None,
        freepik_service=None,
        dry_run: bool = False,
    ):
        self._notion = notion_service
        self._claude = claude_service
        self._google = google_places_service
        self._location = location_service
        self._freepik = freepik_service
        self._dry_run = dry_run

    def create_place_from_query(self, keywords: str) -> dict:
        """Run the places pipeline and create a Notion page from the query."""
        run_id = str(uuid.uuid4())[:8]
        context = PipelineRunContext(
            run_id=run_id,
            initial={
                ContextKeys.RAW_QUERY: keywords,
                "_notion_service": self._notion,
                "_claude_service": self._claude,
                "_google_places_service": self._google,
                "_freepik_service": self._freepik,
                "_location_service": self._location,
                "_dry_run": self._dry_run,
            },
        )
        pipeline_cls = get_global_pipeline("places_global_pipeline")
        if not pipeline_cls:
            raise RuntimeError("places_global_pipeline not registered")
        pipeline = pipeline_cls(db_name=PLACES_DB_NAME)

        keywords_preview = keywords[:50] + ("..." if len(keywords) > 50 else "")
        with log_pipeline_request(run_id, keywords_preview, self._dry_run) as result:
            pipeline.run(context)
            properties = context.get_properties()
            property_sources = context.get_property_sources()
            property_skips = context.get_property_skips()
            icon = context.get(ContextKeys.ICON)
            cover = context.get(ContextKeys.COVER_IMAGE)
            result.property_count = len(properties)
            return self.create_place(
                properties,
                keywords=keywords,
                property_sources=property_sources,
                property_skips=property_skips,
                icon=icon,
                cover=cover,
            )

    def generate_random_entry(self, db_name: str) -> dict:
        """Generate a random property payload from the cached schema (legacy)."""
        schema = self._notion.get_schema(db_name)
        properties: dict = {}

        for prop_name, prop_schema in schema.items():
            value = _build_property_value(prop_name, prop_schema)
            if value is not None:
                properties[prop_name] = value

        return properties

    def _build_dry_run_response(
        self,
        properties: dict,
        keywords: str | None = None,
        *,
        icon: dict | None = None,
        cover: dict | None = None,
    ) -> dict:
        """Build a preview response for dry-run mode."""
        out: dict = {
            "mode": "dry_run",
            "database": PLACES_DB_NAME,
            "properties": properties,
            "summary": {
                "property_count": len(properties),
                "property_names": list(properties.keys()),
            },
            **({"keywords": keywords} if keywords is not None else {}),
        }
        if icon is not None:
            out["icon"] = icon
        if cover is not None:
            out["cover"] = cover
        return out

    def create_place(
        self,
        entry: dict,
        keywords: str | None = None,
        property_sources: dict[str, str] | None = None,
        property_skips: dict[str, str] | None = None,
        *,
        icon: dict | None = None,
        cover: dict | None = None,
    ) -> dict:
        """Create a new place entry in the Places to Visit database."""
        if self._dry_run:
            render_dry_run_table(
                PLACES_DB_NAME,
                entry,
                keywords=keywords,
                property_sources=property_sources,
                property_skips=property_skips,
                icon=icon,
                cover=cover,
            )
            return self._build_dry_run_response(
                entry, keywords=keywords, icon=icon, cover=cover
            )
        data_source_id = self._notion.get_data_source_id(PLACES_DB_NAME)
        return self._notion.create_page(
            data_source_id=data_source_id,
            properties=entry,
            icon=icon,
            cover=cover,
        )
