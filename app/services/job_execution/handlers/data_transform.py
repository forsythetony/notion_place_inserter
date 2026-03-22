"""Data Transform step runtime handler."""

from __future__ import annotations

import re
from typing import Any

from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle
from app.services.job_execution.step_runtime_base import StepRuntime


def _parse_path(path: str) -> list[str | int]:
    """Parse a path like 'photos[0].name' or 'places[0].photos[0].name' into segments."""
    if not path or not isinstance(path, str):
        return []
    segments: list[str | int] = []
    # Split by '.' but respect brackets: "photos[0].name" -> ["photos[0]", "name"]
    parts = path.split(".")
    for p in parts:
        p = p.strip()
        if not p:
            continue
        match = re.match(r"^(\w+)\[(\d+)\]$", p)
        if match:
            segments.append(match.group(1))
            segments.append(int(match.group(2)))
        else:
            segments.append(p)
    return segments


def _extract_at_path(value: Any, segments: list[str | int]) -> Any:
    """Traverse value by segments; return None if path missing."""
    cur: Any = value
    for seg in segments:
        if cur is None:
            return None
        if isinstance(seg, int):
            if not isinstance(cur, list) or seg < 0 or seg >= len(cur):
                return None
            cur = cur[seg]
        else:
            if not isinstance(cur, dict) or seg not in cur:
                return None
            cur = cur[seg]
    return cur


class DataTransformHandler(StepRuntime):
    """Deterministic transform over step input (e.g. extract URL/name from payload)."""

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
        operation = config.get("operation", "extract_key")
        source_path = config.get("source_path", "")
        fallback_value = config.get("fallback_value")

        if operation == "extract_key" and source_path:
            step_handle.log_processing(f"Data transform extract_key (path={source_path!r}).")
            segments = _parse_path(source_path)
            extracted = _extract_at_path(value, segments) if segments else None
            transformed = extracted if extracted is not None else fallback_value
        else:
            step_handle.log_processing(f"Data transform (operation={operation!r}); using fallback.")
            transformed = fallback_value

        return {"transformed_value": transformed}
