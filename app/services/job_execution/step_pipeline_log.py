"""Standardized INPUT / PROCESSING / FINAL logging for pipeline step execution."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from loguru import logger

from app.env_bootstrap import is_pipeline_step_log_verbose, is_pipeline_trace_verbose

# Default max string length in INPUT/FINAL at INFO (longer when verbose env on).
_DEFAULT_STR_MAX = 120
_VERBOSE_STR_MAX = 400


def _str_max_for_input() -> int:
    if is_pipeline_step_log_verbose() or is_pipeline_trace_verbose():
        return _VERBOSE_STR_MAX
    return _DEFAULT_STR_MAX


STEP_TRACE_SCHEMA_VERSION = 1
# Full admin/debug trace (no per-string truncation; JSON-safe only).
STEP_TRACE_FULL_SCHEMA_VERSION = 2


def _json_default_for_db(o: Any) -> Any:
    """Types PostgREST jsonb cannot accept raw; convert to JSON-safe values."""
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, uuid.UUID):
        return str(o)
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, bytes):
        return o.decode("utf-8", errors="replace")
    if isinstance(o, set):
        return list(o)
    if isinstance(o, tuple):
        return list(o)
    return str(o)


def json_safe_for_db(obj: Any) -> Any:
    """Round-trip through JSON so nested structures are PostgREST/Supabase-safe (jsonb)."""
    try:
        return json.loads(
            json.dumps(obj, default=_json_default_for_db, allow_nan=False)
        )
    except (TypeError, ValueError):
        return json.loads(json.dumps(obj, default=str))


def build_step_input_summary(
    log: StepPipelineLog,
    *,
    resolved_inputs: dict[str, Any],
    input_bindings: dict[str, Any],
    config: dict[str, Any],
    max_str: int | None = None,
) -> dict[str, Any]:
    """Structured INPUT payload for DB/API (v1); aligns sanitization with INFO logs."""
    m = max_str if max_str is not None else _str_max_for_input()
    raw = {
        "schema_version": STEP_TRACE_SCHEMA_VERSION,
        "meta": {
            "run_id": log.run_id,
            "job_id": log.job_id,
            "stage_id": log.stage_id,
            "pipeline_id": log.pipeline_id,
            "step_id": log.step_id,
            "step_template_id": log.step_template_id,
        },
        "resolved_inputs": sanitize_for_step_log(dict(resolved_inputs), max_str=m),
        "config": sanitize_for_step_log(dict(config), max_str=m),
        "input_bindings": sanitize_for_step_log(dict(input_bindings), max_str=m),
    }
    return json_safe_for_db(raw)


def build_step_output_summary(
    *,
    outputs: dict[str, Any] | None,
    status: str,
    runtime_ms: float,
    error: str | None = None,
    max_str: int | None = None,
    step_outcome: str | None = None,
    error_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured FINAL payload for DB/API (v1).

    ``status`` is retained for legacy readers (typically ``succeeded`` or ``failed``).
    ``step_outcome`` distinguishes degraded outcomes: ``continued_with_error``,
    ``continued_with_default`` when the executor applies a failure policy.
    """
    m = max_str if max_str is not None else _str_max_for_input()
    out = outputs or {}
    sanitized_outputs = sanitize_for_step_log(dict(out), max_str=m)
    err_out: str | None = None
    if error:
        err_out = error if len(error) <= 2000 else error[:1997] + "..."
    raw: dict[str, Any] = {
        "schema_version": STEP_TRACE_SCHEMA_VERSION,
        "outputs": sanitized_outputs,
        "status": status,
        "runtime_ms": round(runtime_ms, 4),
        "error": err_out,
    }
    if step_outcome:
        raw["step_outcome"] = step_outcome
    if error_detail:
        raw["error_detail"] = json_safe_for_db(dict(error_detail))
    return json_safe_for_db(raw)


def build_step_trace_full(
    log: StepPipelineLog,
    *,
    resolved_inputs: dict[str, Any],
    input_bindings: dict[str, Any],
    config: dict[str, Any],
    outputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full step trace for admin Monitoring (no string truncation; PostgREST-safe JSON)."""
    raw: dict[str, Any] = {
        "schema_version": STEP_TRACE_FULL_SCHEMA_VERSION,
        "meta": {
            "run_id": log.run_id,
            "job_id": log.job_id,
            "stage_id": log.stage_id,
            "pipeline_id": log.pipeline_id,
            "step_id": log.step_id,
            "step_template_id": log.step_template_id,
        },
        "resolved_inputs": json_safe_for_db(dict(resolved_inputs)),
        "input_bindings": json_safe_for_db(dict(input_bindings)),
        "config": json_safe_for_db(dict(config)),
    }
    if outputs is not None:
        raw["outputs"] = json_safe_for_db(dict(outputs))
    return json_safe_for_db(raw)


def sanitize_for_step_log(obj: Any, *, max_str: int | None = None) -> Any:
    """Recursively copy structures; truncate strings longer than ``max_str``."""
    m = max_str if max_str is not None else _str_max_for_input()
    if isinstance(obj, str):
        if len(obj) <= m:
            return obj
        return obj[: m - 3] + "..."
    if isinstance(obj, dict):
        return {k: sanitize_for_step_log(v, max_str=m) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_step_log(v, max_str=m) for v in obj]
    if isinstance(obj, tuple):
        return tuple(sanitize_for_step_log(v, max_str=m) for v in obj)
    return obj


def _format_kv_lines(data: dict[str, Any], *, max_str: int) -> list[str]:
    lines: list[str] = []
    if not data:
        return ["  (none)"]
    for k in sorted(data.keys()):
        v = data[k]
        sanitized = sanitize_for_step_log(v, max_str=max_str)
        if isinstance(sanitized, (dict, list)):
            try:
                blob = json.dumps(sanitized, ensure_ascii=False, default=str)
            except TypeError:
                blob = str(sanitized)
            if len(blob) > max_str * 3:
                blob = blob[: max_str * 3 - 3] + "..."
            lines.append(f"  - {k}: {blob}")
        else:
            lines.append(f"  - {k}: {sanitized}")
    return lines


@dataclass
class StepPipelineLog:
    """Per-step logger bound to orchestration ids; use via ``StepExecutionHandle.log_processing``."""

    run_id: str
    job_id: str
    stage_id: str
    pipeline_id: str
    step_id: str
    step_template_id: str
    processing_lines: list[str] = field(default_factory=list)

    def processing(self, message: str) -> None:
        self.processing_lines.append(message)
        logger.info(
            "pipeline_step | PROCESSING | run_id={} | job_id={} | stage_id={} | pipeline_id={} | "
            "step_id={} | template={} | {}",
            self.run_id,
            self.job_id,
            self.stage_id,
            self.pipeline_id,
            self.step_id,
            self.step_template_id,
            message,
        )


def emit_step_input(
    log: StepPipelineLog,
    *,
    resolved_inputs: dict[str, Any],
    input_bindings: dict[str, Any],
    config: dict[str, Any],
) -> None:
    """Emit INPUT block at INFO; optional DEBUG lines for bindings when trace/verbose."""
    max_str = _str_max_for_input()
    header = (
        "pipeline_step | INPUT | run_id={} | job_id={} | stage_id={} | pipeline_id={} | "
        "step_id={} | template={}"
    ).format(
        log.run_id,
        log.job_id,
        log.stage_id,
        log.pipeline_id,
        log.step_id,
        log.step_template_id,
    )
    body_lines: list[str] = [header, "INPUT LOG:", "Input:"]
    body_lines.extend(_format_kv_lines(dict(resolved_inputs), max_str=max_str))
    body_lines.append("Config values:")
    body_lines.extend(_format_kv_lines(dict(config), max_str=max_str))
    logger.info("\n".join(body_lines))

    if is_pipeline_trace_verbose() or is_pipeline_step_log_verbose():
        try:
            b_json = json.dumps(
                sanitize_for_step_log(dict(input_bindings), max_str=max_str),
                ensure_ascii=False,
                default=str,
            )
            lim = os.environ.get("WORKER_DEBUG_PAYLOAD_JSON_MAX_CHARS", "").strip()
            if lim:
                try:
                    n = int(lim)
                    if n > 0 and len(b_json) > n:
                        b_json = b_json[:n] + f"... [truncated, total_len={len(b_json)}]"
                except ValueError:
                    pass
            logger.debug(
                "pipeline_step | INPUT | bindings_json | run_id={} | step_id={} | {}",
                log.run_id,
                log.step_id,
                b_json,
            )
        except Exception:
            logger.debug(
                "pipeline_step | INPUT | bindings_json | run_id={} | step_id={} | <unserializable>",
                log.run_id,
                log.step_id,
            )


def emit_step_final(
    log: StepPipelineLog,
    *,
    outputs: dict[str, Any] | None,
    status: str,
    runtime_ms: float,
    error: str | None = None,
) -> None:
    """Emit FINAL block at INFO."""
    max_str = _str_max_for_input()
    out = outputs or {}
    header = (
        "pipeline_step | FINAL | run_id={} | job_id={} | stage_id={} | pipeline_id={} | "
        "step_id={} | template={}"
    ).format(
        log.run_id,
        log.job_id,
        log.stage_id,
        log.pipeline_id,
        log.step_id,
        log.step_template_id,
    )
    lines: list[str] = [header, "FINAL LOG:", "Output:"]
    if not out:
        lines.append("  (none)")
    else:
        for k in sorted(out.keys()):
            v = out[k]
            sanitized = sanitize_for_step_log(v, max_str=max_str)
            if isinstance(sanitized, (dict, list)):
                try:
                    blob = json.dumps(sanitized, ensure_ascii=False, default=str)
                except TypeError:
                    blob = str(sanitized)
                if len(blob) > max_str * 4:
                    blob = blob[: max_str * 4 - 3] + "..."
                lines.append(f"  - {k}: {blob}")
            else:
                lines.append(f"  - {k}: {sanitized}")
    lines.append(f"Status: {status}")
    lines.append(f"Runtime_ms: {runtime_ms:.2f}")
    if error:
        err_preview = error if len(error) <= 2000 else error[:1997] + "..."
        lines.append(f"Error: {err_preview}")
    logger.info("\n".join(lines))
