"""Templater step runtime handler."""

from __future__ import annotations

import re
from typing import Any

from app.services.job_execution.binding_resolver import resolve_binding
from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.step_runtime_base import StepRuntime


def _render_template(template: str, values: dict[str, str]) -> str:
    """Replace {{key}} placeholders with values. Missing keys become empty string."""
    if not template:
        return ""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, "")

    return re.sub(r"\{\{(\w+)\}\}", repl, template)


class TemplaterHandler(StepRuntime):
    """Render a string from a template and configurable values. Values can reference cache or signals."""

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        input_bindings: dict[str, Any],
        resolved_inputs: dict[str, Any],
        ctx: ExecutionContext,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        template = config.get("template") or ""
        raw_values = config.get("values") or {}

        if not isinstance(raw_values, dict):
            raw_values = {}

        resolved: dict[str, str] = {}
        for key, binding in raw_values.items():
            if not isinstance(key, str):
                continue
            if isinstance(binding, dict):
                val = resolve_binding(binding, ctx, snapshot)
            else:
                val = binding
            if val is None:
                resolved[key] = ""
            elif isinstance(val, (str, int, float)):
                resolved[key] = str(val)
            else:
                resolved[key] = str(val)

        ctx.log_step_processing(
            f"Rendering template (placeholder_keys={sorted(resolved.keys())!s})."
        )
        rendered = _render_template(template, resolved)
        return {"rendered_value": rendered}
