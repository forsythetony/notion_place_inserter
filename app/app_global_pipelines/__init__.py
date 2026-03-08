"""Registry of GlobalPipeline implementations."""

from app.app_global_pipelines.places_to_visit import PlacesGlobalPipeline

REGISTRY: dict[str, type] = {
    "places_global_pipeline": PlacesGlobalPipeline,
}


def get_global_pipeline(pipeline_id: str) -> type | None:
    """Return the GlobalPipeline class for the given id, or None."""
    return REGISTRY.get(pipeline_id)
