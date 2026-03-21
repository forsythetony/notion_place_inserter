"""Execution context and types for snapshot-driven job runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.job_execution.step_pipeline_log import StepPipelineLog


@dataclass
class ExecutionContext:
    """
    Mutable run-scoped state for a single job execution.
    Holds trigger payload, step outputs, run cache, and final property map.
    """

    run_id: str
    job_id: str
    definition_snapshot_ref: str | None
    trigger_payload: dict[str, Any]
    dry_run: bool = False
    owner_user_id: str = ""

    # Current step run id (set during step execution for usage attribution)
    step_run_id: str | None = None

    # Set only for the duration of ``_run_step``; used by ``log_step_processing``.
    step_pipeline_log: StepPipelineLog | None = None

    # Step outputs: step_id -> {output_name: value}
    step_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Run-scoped shared cache (key -> value)
    run_cache: dict[str, Any] = field(default_factory=dict)

    # Final Notion property map (schema_property_id or external name -> value)
    properties: dict[str, Any] = field(default_factory=dict)

    # Page metadata (icon, cover)
    icon: dict[str, Any] | None = None
    cover: dict[str, Any] | None = None

    # Injected service refs (claude, google, notion, usage_accounting, etc.)
    _services: dict[str, Any] = field(default_factory=dict, repr=False)

    # Live test / editor run policy (default: production-like full writes)
    allow_destination_writes: bool = True
    invocation_source: str | None = None
    # When set, _run_step asserts step location is inside these id sets (defense in depth).
    scope_boundary: dict[str, Any] | None = None
    # Per call_site_id: {"enabled": bool, "manual_response": Any} for network suppression.
    api_overrides: dict[str, Any] = field(default_factory=dict)

    def get_service(self, name: str) -> Any:
        return self._services.get(name)

    def set_step_output(self, step_id: str, output_name: str, value: Any) -> None:
        if step_id not in self.step_outputs:
            self.step_outputs[step_id] = {}
        self.step_outputs[step_id][output_name] = value

    def get_step_output(self, step_id: str, output_name: str) -> Any:
        return (self.step_outputs.get(step_id) or {}).get(output_name)

    def set_property(self, schema_property_id: str, value: Any) -> None:
        self.properties[schema_property_id] = value

    def log_step_processing(self, message: str) -> None:
        """Emit a standardized PROCESSING line for the current step (no-op if not in a step run)."""
        spl = self.step_pipeline_log
        if spl is not None:
            spl.processing(message)
