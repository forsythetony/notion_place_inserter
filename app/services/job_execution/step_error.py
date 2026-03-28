"""Normalize exceptions into structured step error payloads for persistence and logs."""

from __future__ import annotations

import traceback
from typing import Any

# Executor-level policies (StepInstance.failure_policy)
FAILURE_POLICY_FAIL = "fail"
FAILURE_POLICY_CONTINUE = "continue"
FAILURE_POLICY_CONTINUE_WITH_DEFAULT = "continue_with_default"

def normalize_failure_policy(raw: str | None) -> str:
    """
    Return canonical failure policy. Unknown values default to fail (safe).
    """
    if raw is None or raw == "":
        return FAILURE_POLICY_FAIL
    s = str(raw).strip().lower()
    if s in (
        FAILURE_POLICY_FAIL,
        FAILURE_POLICY_CONTINUE,
        FAILURE_POLICY_CONTINUE_WITH_DEFAULT,
    ):
        return s
    return FAILURE_POLICY_FAIL


def build_step_error_detail(
    exc: BaseException,
    *,
    step_id: str,
    step_template_id: str,
    stage_id: str,
    pipeline_id: str,
    failure_policy: str,
    provider: str | None = None,
    retryable: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Structured error for step_runs.error_detail and output_summary.
    Schema version 1 — keep JSON-serializable values only.
    """
    tb = traceback.format_exc()
    detail: dict[str, Any] = {
        "schema_version": 1,
        "type": type(exc).__name__,
        "message": str(exc)[:4000],
        "step_id": step_id,
        "step_template_id": step_template_id,
        "stage_id": stage_id,
        "pipeline_id": pipeline_id,
        "failure_policy": failure_policy,
    }
    if provider:
        detail["provider"] = provider
    if retryable is not None:
        detail["retryable"] = retryable
    if tb and tb.strip() != "NoneType: None":
        detail["traceback"] = tb[-12000:] if len(tb) > 12000 else tb
    if extra:
        detail["context"] = extra
    return detail


def infer_provider_for_exception(exc: BaseException) -> str | None:
    """Best-effort provider label for structured errors (avoid import cycles in callers)."""
    from app.services.freepik_service import FreepikAPIError

    if isinstance(exc, FreepikAPIError):
        return "freepik"
    return None


def infer_retryable_for_exception(exc: BaseException) -> bool | None:
    """Heuristic retry hint for transient HTTP failures."""
    from app.services.freepik_service import FreepikAPIError

    if isinstance(exc, FreepikAPIError):
        code = exc.status_code
        if code is None:
            return None
        return code in (408, 429, 500, 502, 503, 504)
    return None


def default_outputs_for_step(
    step_template_id: str,
    *,
    resolved_inputs: dict[str, Any],
) -> dict[str, Any]:
    """
    Template-shaped defaults when failure_policy is continue_with_default.
    Extend as new optional steps need deterministic fallbacks.
    """
    if step_template_id == "step_template_search_icons":
        return {"image_url": None}
    if step_template_id == "step_template_upload_image_to_notion":
        return {"notion_image_url": None}
    if step_template_id == "step_template_optimize_input_claude":
        q = resolved_inputs.get("query")
        return {"optimized_query": str(q).strip() if q is not None else ""}
    if step_template_id == "step_template_property_set":
        return {}
    return {}
