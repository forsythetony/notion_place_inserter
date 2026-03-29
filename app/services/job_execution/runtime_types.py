"""Execution context and types for snapshot-driven job runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from app.services.job_execution.step_pipeline_log import StepPipelineLog

StepExecutionOutcome = Literal["success", "degraded", "failed"]

# Max chars for previews embedded in processing_log strings (align with optimize_input-style caps).
_SERVICE_TRACE_PREVIEW_MAX = 2500


def _service_trace_preview(text: str | None, *, max_len: int = _SERVICE_TRACE_PREVIEW_MAX) -> str:
    s = text if text is not None else ""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


class ServiceCallTrace(TypedDict, total=False):
    """
    Optional structured metadata from an external service for step processing logs.

    Handlers typically pass this through :meth:`StepExecutionHandle` helpers rather than
    building log strings ad hoc.
    """

    service: str
    operation: str
    status: Literal["started", "succeeded", "failed"]
    model: str
    max_tokens: int
    request_preview: str
    response_preview: str
    input_tokens: int
    output_tokens: int


@dataclass
class StepExecutionResult:
    """
    Optional structured return from ``StepRuntime.execute``.

    Handlers may still return a plain ``dict`` of outputs (backward compatible).

    - ``success``: normal completion; same semantics as returning a dict.
    - ``degraded``: step completed with fallback outputs; diagnostics are persisted
      (processing log, ``error_detail``, ``output_summary.step_outcome``) without raising.
    - ``failed``: same as a raised exception for pipeline failure (step run ``failed``,
      then re-raise so the job fails); respects ``failure_policy`` like an exception
      (e.g. ``continue_with_default`` can still recover).
    """

    outputs: dict[str, Any] = field(default_factory=dict)
    outcome: StepExecutionOutcome = "success"
    error_message: str | None = None
    error_detail: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class StepExecutionHandle:
    """
    Per-step execution scope passed into handlers. Safe under parallel pipelines:
    usage and processing lines use this handle instead of mutable fields on shared ExecutionContext.
    """

    step_run_id: str
    pipeline_log: StepPipelineLog

    def log_processing(self, message: str) -> None:
        """Append a PROCESSING line for this step only."""
        self.pipeline_log.processing(message)

    def log_step_runtime_calling_service(
        self,
        *,
        service_label: str,
        operation: str,
        config_summary: str,
    ) -> None:
        """Log that the step runtime is invoking a named service with a config summary."""
        self.log_processing(
            f"[StepRuntime] Calling {service_label} {operation} with following config: "
            f"{_service_trace_preview(config_summary)}"
        )

    def log_service_provider_llm_request(
        self,
        *,
        service_label: str,
        model: str,
        max_tokens: int | None,
        body_preview: str,
    ) -> None:
        """Log an LLM request as seen by the service layer (after the call, from trace)."""
        mt = max_tokens if max_tokens is not None else "None"
        self.log_processing(
            f"[{service_label}] Calling prompt with model `{model}`, maxTokens `{mt}` and body "
            f"`{_service_trace_preview(body_preview)}`"
        )

    def log_service_provider_llm_success(
        self,
        *,
        service_label: str,
        response_preview: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        """Log a successful LLM response preview and token usage."""
        self.log_processing(
            f"[{service_label}] Successful response of `{_service_trace_preview(response_preview)}` "
            f"with tokens consumed in={input_tokens} out={output_tokens}"
        )

    def log_step_runtime_received_success(self) -> None:
        self.log_processing("[StepRuntime] Received successful response")

    def log_step_runtime_transforming(self, *, from_preview: str, to_preview: str) -> None:
        """Log post-processing of the raw model output (e.g. limit_words)."""
        self.log_processing(
            f"[StepRuntime] Transforming response `{_service_trace_preview(from_preview)}` into "
            f"`{_service_trace_preview(to_preview)}`"
        )


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
