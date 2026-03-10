"""Pipeline run context: shared state and typed key helpers."""

from contextvars import ContextVar
from typing import Any

# Thread-safe active pipeline identity for provenance. Set by orchestration.
_active_pipeline_id: ContextVar[str | None] = ContextVar(
    "active_pipeline_id", default=None
)


def get_active_pipeline_id() -> str | None:
    """Return the pipeline_id of the currently executing pipeline, if any."""
    return _active_pipeline_id.get()


def set_active_pipeline_id(pipeline_id: str | None) -> None:
    """Set the active pipeline_id for provenance. Used by orchestration."""
    _active_pipeline_id.set(pipeline_id)


class ContextKeys:
    """Convention-enforced keys for pipeline context. Use these to avoid typos."""

    RUN_ID = "run_id"
    RAW_QUERY = "raw_query"
    REWRITTEN_QUERY = "rewritten_query"
    GOOGLE_PLACE = "google_place"
    SCHEMA = "schema"
    PROPERTIES = "properties"
    PROPERTY_SOURCES = "property_sources"
    PROPERTY_SKIPS = "property_skips"
    PROPERTY_OMISSIONS = "property_omissions"
    COVER_IMAGE = "cover_image"
    ICON = "icon"


class PipelineRunContext:
    """
    Shared state for a single pipeline run.
    Stage pipelines and property pipelines communicate through this object.
    """

    def __init__(self, run_id: str, initial: dict[str, Any] | None = None):
        self._data: dict[str, Any] = dict(initial or {})
        self._data[ContextKeys.RUN_ID] = run_id
        if ContextKeys.PROPERTIES not in self._data:
            self._data[ContextKeys.PROPERTIES] = {}
        if ContextKeys.PROPERTY_SOURCES not in self._data:
            self._data[ContextKeys.PROPERTY_SOURCES] = {}
        if ContextKeys.PROPERTY_SKIPS not in self._data:
            self._data[ContextKeys.PROPERTY_SKIPS] = {}
        if ContextKeys.PROPERTY_OMISSIONS not in self._data:
            self._data[ContextKeys.PROPERTY_OMISSIONS] = {}

    @property
    def run_id(self) -> str:
        return self._data.get(ContextKeys.RUN_ID, "")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def set_property(self, name: str, value: Any, source_pipeline: str | None = None) -> None:
        """Set a resolved property value. Records pipeline provenance when available."""
        props = self._data.get(ContextKeys.PROPERTIES, {})
        props[name] = value
        self._data[ContextKeys.PROPERTIES] = props

        pipeline_id = source_pipeline or get_active_pipeline_id()
        if pipeline_id:
            sources = self._data.get(ContextKeys.PROPERTY_SOURCES, {})
            sources[name] = pipeline_id
            self._data[ContextKeys.PROPERTY_SOURCES] = sources

    def mark_property_skipped(self, name: str, source_pipeline: str | None = None) -> None:
        """Record that a property was intentionally skipped (NoOp). Does not add to payload."""
        pipeline_id = source_pipeline or get_active_pipeline_id()
        if pipeline_id:
            skips = self._data.get(ContextKeys.PROPERTY_SKIPS, {})
            skips[name] = pipeline_id
            self._data[ContextKeys.PROPERTY_SKIPS] = skips

    def mark_property_omitted(
        self,
        name: str,
        *,
        reason: str = "no_value",
        source_pipeline: str | None = None,
    ) -> None:
        """Record that a property pipeline ran but intentionally produced no output value."""
        pipeline_id = source_pipeline or get_active_pipeline_id()
        if pipeline_id:
            omissions = self._data.get(ContextKeys.PROPERTY_OMISSIONS, {})
            omissions[name] = {"pipeline_id": pipeline_id, "reason": reason}
            self._data[ContextKeys.PROPERTY_OMISSIONS] = omissions

    def get_property_skips(self) -> dict[str, str]:
        """Return mapping of property name -> pipeline_id that skipped it."""
        return dict(self._data.get(ContextKeys.PROPERTY_SKIPS, {}))

    def get_property_omissions(self) -> dict[str, dict[str, str]]:
        """
        Return mapping of property name -> omission metadata.
        Example: {"Neighborhood": {"pipeline_id": "neighborhood_Neighborhood", "reason": "no_value"}}
        """
        return dict(self._data.get(ContextKeys.PROPERTY_OMISSIONS, {}))

    def get_property_sources(self) -> dict[str, str]:
        """Return mapping of property name -> pipeline_id that resolved it."""
        return dict(self._data.get(ContextKeys.PROPERTY_SOURCES, {}))

    def get_properties(self) -> dict[str, Any]:
        """Return the resolved Notion properties dict."""
        return dict(self._data.get(ContextKeys.PROPERTIES, {}))

    def snapshot(self) -> dict[str, Any]:
        """Return a copy of context data for debugging or AI prompts."""
        return dict(self._data)
