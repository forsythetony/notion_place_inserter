"""Property Set step runtime handler."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle
from app.services.job_execution.step_runtime_base import StepRuntime

_ALLOWED_PAGE_METADATA_FIELDS = frozenset({"cover_image", "icon_image"})


class PropertySetHandler(StepRuntime):
    """Write value to target schema property or page metadata (terminal step)."""

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        input_bindings: dict[str, Any],
        resolved_inputs: dict[str, Any],
        ctx: ExecutionContext,
        step_handle: StepExecutionHandle,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        value = resolved_inputs.get("value")
        target_kind = config.get("target_kind", "schema_property")

        if not getattr(ctx, "allow_destination_writes", True):
            if target_kind == "page_metadata":
                step_handle.log_processing(
                    "Skipping page_metadata property_set (live test: destination writes disabled)."
                )
                logger.info(
                    "property_set_skipped | step_id={} target_kind=page_metadata reason=no_destination_writes",
                    step_id,
                )
                return {}
            raise ValueError(
                "Property Set to schema is disabled for this live test run "
                "(allow_destination_writes=False). Use a full job configuration to write to Notion."
            )

        if target_kind == "page_metadata":
            step_handle.log_processing(
                f"Setting page metadata (target_field={config.get('target_field')!r})."
            )
            target_field = config.get("target_field")
            if target_field in _ALLOWED_PAGE_METADATA_FIELDS and value is not None:
                payload = self._to_notion_metadata_payload(value)
                if payload is not None:
                    if target_field == "cover_image":
                        ctx.cover = payload
                    elif target_field == "icon_image":
                        ctx.icon = payload
            return {}

        schema_property_id = config.get("schema_property_id")
        if schema_property_id is not None:
            step_handle.log_processing(f"Recording property for page payload (schema_property_id={schema_property_id!r}).")
            ctx.set_property(schema_property_id, value)
        return {}

    def _to_notion_metadata_payload(self, value: Any) -> dict[str, Any] | None:
        """Convert value to Notion icon/cover payload (external or file_upload)."""
        if isinstance(value, dict):
            if value.get("type") in ("external", "file", "file_upload"):
                return value
            ext = value.get("external") or {}
            if isinstance(ext, dict) and ext.get("url"):
                return {"type": "external", "external": {"url": ext["url"]}}
        if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
            return {"type": "external", "external": {"url": value.strip()}}
        return None
