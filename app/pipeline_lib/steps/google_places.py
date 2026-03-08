"""Reusable property steps that extract from Google Places data."""

from app.pipeline_lib.context import ContextKeys, PipelineRunContext
from app.pipeline_lib.core import PipelineStep
from app.pipeline_lib.logging import log_step


class ExtractDisplayName(PipelineStep):
    """Extract displayName from google_place in context."""

    @property
    def step_id(self) -> str:
        return "extract_display_name"

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
        ):
            place = context.get(ContextKeys.GOOGLE_PLACE)
            if not place:
                return None
            return place.get("displayName", "")


class ExtractFormattedAddress(PipelineStep):
    """Extract formattedAddress from google_place in context."""

    @property
    def step_id(self) -> str:
        return "extract_formatted_address"

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
        ):
            place = context.get(ContextKeys.GOOGLE_PLACE)
            if not place:
                return None
            return place.get("formattedAddress", "")


class ExtractWebsiteUri(PipelineStep):
    """Extract websiteUri from google_place in context."""

    @property
    def step_id(self) -> str:
        return "extract_website_uri"

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
        ):
            place = context.get(ContextKeys.GOOGLE_PLACE)
            if not place:
                return None
            return place.get("websiteUri", "")


class ExtractGoogleMapsUri(PipelineStep):
    """Extract googleMapsUri from google_place in context. Falls back to place_id URL if absent."""

    @property
    def step_id(self) -> str:
        return "extract_google_maps_uri"

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
        ):
            place = context.get(ContextKeys.GOOGLE_PLACE)
            if not place:
                return None
            uri = place.get("googleMapsUri", "") or ""
            if uri:
                return uri
            place_id = place.get("id", "")
            if place_id:
                return f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            return None


class ExtractRating(PipelineStep):
    """Extract rating from google_place in context."""

    @property
    def step_id(self) -> str:
        return "extract_rating"

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
        ):
            place = context.get(ContextKeys.GOOGLE_PLACE)
            if not place:
                return None
            return place.get("rating")


class ExtractLatitude(PipelineStep):
    """Extract latitude from google_place in context. Returns float or None."""

    @property
    def step_id(self) -> str:
        return "extract_latitude"

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
        ):
            place = context.get(ContextKeys.GOOGLE_PLACE)
            if not place:
                return None
            lat = place.get("latitude")
            if lat is None:
                return None
            try:
                return float(lat)
            except (TypeError, ValueError):
                return None


class ExtractLongitude(PipelineStep):
    """Extract longitude from google_place in context. Returns float or None."""

    @property
    def step_id(self) -> str:
        return "extract_longitude"

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
        ):
            place = context.get(ContextKeys.GOOGLE_PLACE)
            if not place:
                return None
            lng = place.get("longitude")
            if lng is None:
                return None
            try:
                return float(lng)
            except (TypeError, ValueError):
                return None


class ExtractCoordinates(PipelineStep):
    """Extract coordinates as '<lat>, <lng>' from google_place. Returns str or None."""

    @property
    def step_id(self) -> str:
        return "extract_coordinates"

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
        ):
            place = context.get(ContextKeys.GOOGLE_PLACE)
            if not place:
                return None
            lat = place.get("latitude")
            lng = place.get("longitude")
            if lat is None or lng is None:
                return None
            try:
                return f"{float(lat)}, {float(lng)}"
            except (TypeError, ValueError):
                return None
