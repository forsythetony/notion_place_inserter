"""Places to Visit global pipeline: research -> property_resolution -> image_resolution."""

from loguru import logger

from app.custom_pipelines import CUSTOM_PIPELINE_REGISTRY
from app.models.schema import DatabaseSchema
from app.pipeline_lib.context import ContextKeys, PipelineRunContext
from app.pipeline_lib.core import GlobalPipeline, Pipeline, PipelineStep, Stage
from app.pipeline_lib.default import DefaultPipeline, SKIP_TYPES
from app.pipeline_lib.logging import log_step
from app.pipeline_lib.stage_pipelines.google_places import QueryToGoogleCachePipeline
from app.pipeline_lib.stage_pipelines.schema import LoadLatestSchemaPipeline


PLACES_DB_NAME = "Places to Visit"


class ResearchStage(Stage):
    """Stage 1: load schema + rewrite query + Google Places fetch."""

    def __init__(self, db_name: str):
        self._db_name = db_name

    @property
    def stage_id(self) -> str:
        return "research"

    def _pipelines_impl(self, context: PipelineRunContext | None) -> list[Pipeline]:
        return [
            LoadLatestSchemaPipeline(self._db_name),
            QueryToGoogleCachePipeline(),
        ]


class PropertyResolutionStage(Stage):
    """Stage 2: fan out one pipeline per property (custom or default)."""

    def __init__(self, db_name: str):
        self._db_name = db_name

    @property
    def stage_id(self) -> str:
        return "property_resolution"

    @property
    def run_mode(self) -> str:
        return "parallel"

    def _pipelines_impl(self, context: PipelineRunContext | None) -> list[Pipeline]:
        if not context:
            return []
        schema: DatabaseSchema | None = context.get(ContextKeys.SCHEMA)
        if not schema:
            return []
        pipelines: list[Pipeline] = []
        for prop_name, prop_schema in schema.properties.items():
            custom_cls = CUSTOM_PIPELINE_REGISTRY.get(prop_name)
            if custom_cls:
                pipelines.append(custom_cls(prop_name, prop_schema))
            elif prop_schema.type in SKIP_TYPES:
                continue
            else:
                pipelines.append(DefaultPipeline(prop_name, prop_schema))
        return pipelines


class ResolveCoverFromGooglePhotosStep(PipelineStep):
    """Resolve first Google Place photo to a Notion-ready cover payload.
    Fetches image bytes and uploads to Notion via File Upload API, since Google's
    photoUri URLs often return 400 when accessed directly by Notion or browsers.
    In dry-run mode, resolves an external URL instead of uploading.
    """

    @property
    def step_id(self) -> str:
        return "resolve_cover_from_google_photos"

    def execute(self, context: PipelineRunContext, current_value: object) -> object:
        with log_step(
            context.run_id,
            context.get("_global_pipeline_id", ""),
            context.get("_current_stage_id", ""),
            context.get("_current_pipeline_id", ""),
            self.step_id,
            step_name=self.name,
            step_description=self.description or None,
        ):
            place = context.get(ContextKeys.GOOGLE_PLACE)
            google = context.get("_google_places_service")
            notion = context.get("_notion_service")
            if not place or not google:
                return None
            photos = place.get("photos") or []
            if not photos:
                return None
            first_photo = photos[0]
            photo_name = first_photo.get("name") if isinstance(first_photo, dict) else None
            if not photo_name:
                return None

            dry_run = context.get("_dry_run", False)
            if dry_run:
                url = google.get_photo_url(photo_name)
                if not url:
                    logger.warning(
                        "cover_dry_run_url_resolution_failed | run_id={} photo_name={}",
                        context.run_id,
                        photo_name,
                    )
                    return None
                payload = {"type": "external", "external": {"url": url}}
                context.set(ContextKeys.COVER_IMAGE, payload)
                logger.info(
                    "cover_dry_run_url_resolved | run_id={} photo_name={}",
                    context.run_id,
                    photo_name,
                )
                return payload

            if not notion:
                return None
            logger.info(
                "cover_upload_attempt | run_id={} dry_run={} photo_name={}",
                context.run_id,
                dry_run,
                photo_name,
            )
            image_bytes = google.get_photo_bytes(photo_name)
            if not image_bytes:
                logger.warning(
                    "cover_upload_skipped_no_image_bytes | run_id={} dry_run={} photo_name={}",
                    context.run_id,
                    dry_run,
                    photo_name,
                )
                return None
            payload = notion.upload_cover_from_bytes(image_bytes)
            if not payload:
                logger.warning(
                    "cover_upload_failed | run_id={} dry_run={} photo_name={}",
                    context.run_id,
                    dry_run,
                    photo_name,
                )
                return None

            context.set(ContextKeys.COVER_IMAGE, payload)
            upload_id = (
                payload.get("file_upload", {}).get("id", "")
                if isinstance(payload, dict)
                else ""
            )
            logger.info(
                "cover_upload_success | run_id={} dry_run={} upload_id={}",
                context.run_id,
                dry_run,
                upload_id,
            )
            return payload


class ResolveCoverImagePipeline(Pipeline):
    """Pipeline to resolve cover image from Google Places photos."""

    @property
    def pipeline_id(self) -> str:
        return "resolve_cover_image"

    def steps(self) -> list[PipelineStep]:
        return [ResolveCoverFromGooglePhotosStep()]


class ResolveIconEmojiStep(PipelineStep):
    """Use Claude to generate a Freepik search term, then fetch first icon from Freepik API.
    When Freepik is unavailable (e.g. no API key), falls back to emoji in dry run so the icon
    is still resolved and displayed in the rendered table."""
    @property
    def step_id(self) -> str:
        return "resolve_icon_emoji"

    def execute(self, context: PipelineRunContext, current_value: object) -> object:
        with log_step(
            context.run_id,
            context.get("_global_pipeline_id", ""),
            context.get("_current_stage_id", ""),
            context.get("_current_pipeline_id", ""),
            self.step_id,
            step_name=self.name,
            step_description=self.description or None,
        ):
            place = context.get(ContextKeys.GOOGLE_PLACE)
            claude = context.get("_claude_service")
            freepik = context.get("_freepik_service")
            if not place or not claude:
                return None
            candidate_context = {
                "displayName": place.get("displayName"),
                "primaryType": place.get("primaryType"),
                "types": place.get("types", []),
                "generativeSummary": place.get("generativeSummary"),
                "editorialSummary": place.get("editorialSummary"),
            }
            # Prefer Freepik when available
            if freepik:
                search_term = claude.choose_icon_search_term_for_place(candidate_context)
                if search_term:
                    icon_url = freepik.get_first_icon_url(search_term)
                    if icon_url:
                        payload = {"type": "external", "external": {"url": icon_url}}
                        context.set(ContextKeys.ICON, payload)
                        return payload
            # Fallback to emoji when Freepik unavailable or returns nothing (e.g. dry run without API key)
            dry_run = context.get("_dry_run", False)
            if dry_run:
                emoji = claude.choose_emoji_for_place(candidate_context)
                if emoji:
                    payload = {"type": "emoji", "emoji": emoji}
                    context.set(ContextKeys.ICON, payload)
                    return payload
            return None


class ResolveIconEmojiPipeline(Pipeline):
    """Pipeline to resolve page icon via Claude + Freepik (first result)."""

    @property
    def pipeline_id(self) -> str:
        return "resolve_icon_emoji"

    def steps(self) -> list[PipelineStep]:
        return [ResolveIconEmojiStep()]


class ImageResolutionStage(Stage):
    """Stage 3: resolve cover image and icon emoji."""

    @property
    def stage_id(self) -> str:
        return "image_resolution"

    def _pipelines_impl(self, context: PipelineRunContext | None) -> list[Pipeline]:
        return [ResolveCoverImagePipeline(), ResolveIconEmojiPipeline()]


class PlacesGlobalPipeline(GlobalPipeline):
    """Global pipeline for creating Places to Visit entries from unstructured text."""

    def __init__(self, db_name: str = PLACES_DB_NAME):
        self._db_name = db_name

    @property
    def pipeline_id(self) -> str:
        return "places_global_pipeline"

    @property
    def schema_binding(self) -> str:
        return self._db_name

    def stages(self) -> list[Stage]:
        return [
            ResearchStage(self._db_name),
            PropertyResolutionStage(self._db_name),
            ImageResolutionStage(),
        ]
