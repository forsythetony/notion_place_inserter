"""Resolve input bindings: signal_ref, cache_key_ref, static_value, target_schema_ref."""

from __future__ import annotations

from typing import Any

from app.services.job_execution.runtime_types import ExecutionContext


def resolve_binding(
    binding: dict[str, Any],
    ctx: ExecutionContext,
    snapshot: dict[str, Any],
) -> Any:
    """
    Resolve a single input binding to a value.
    Binding shapes:
    - signal_ref: "trigger.payload.keywords" | "trigger.payload.raw_input" (deprecated) | "step.step_id.output_name"
    - cache_key_ref: {"cache_key": "...", "path": "optional.dot.path"}  # path: nested field under cached value
    - static_value: literal value
    - target_schema_ref: {"schema_property_id": "...", "field": "options"} (data_target_id optional, defaults to job target)
    """
    if not binding or not isinstance(binding, dict):
        return None

    if "signal_ref" in binding:
        return _resolve_signal_ref(binding["signal_ref"], ctx)
    if "cache_key_ref" in binding:
        ref = binding["cache_key_ref"]
        if not isinstance(ref, dict):
            return None
        key = ref.get("cache_key")
        base = ctx.run_cache.get(key) if key else None
        path_str = ref.get("path")
        if path_str and isinstance(path_str, str) and path_str.strip():
            parts = [p for p in path_str.strip().split(".") if p]
            return _resolve_path(base, parts) if parts else base
        return base
    if "cache_key" in binding:
        return ctx.run_cache.get(binding["cache_key"])
    if "static_value" in binding:
        return binding["static_value"]
    if "target_schema_ref" in binding:
        return _resolve_target_schema_ref(binding["target_schema_ref"], snapshot)

    # Allowable_values_source can nest target_schema_ref
    if "allowable_values_source" in binding:
        src = binding["allowable_values_source"]
        if isinstance(src, dict) and "target_schema_ref" in src:
            return _resolve_target_schema_ref(src["target_schema_ref"], snapshot)

    return None


def resolve_input_bindings(
    input_bindings: dict[str, Any],
    ctx: ExecutionContext,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Resolve all input bindings for a step. Returns dict of input_name -> value."""
    resolved: dict[str, Any] = {}
    for name, binding in (input_bindings or {}).items():
        if isinstance(binding, dict):
            resolved[name] = resolve_binding(binding, ctx, snapshot)
        else:
            resolved[name] = binding
    return resolved


def _resolve_signal_ref(ref: str, ctx: ExecutionContext) -> Any:
    """Resolve signal_ref like trigger.payload.keywords or step.step_id.output_name."""
    if not ref or not isinstance(ref, str):
        return None
    parts = ref.split(".")
    if len(parts) < 2:
        return None

    if parts[0] == "trigger":
        return _resolve_trigger_ref(parts[1:], ctx.trigger_payload)
    if parts[0] == "step" and len(parts) >= 3:
        step_id = parts[1]
        output_name = parts[2]
        out = ctx.get_step_output(step_id, output_name)
        if len(parts) == 3:
            return out
        return _resolve_path(out, parts[3:])
    return None


def _resolve_trigger_ref(parts: list[str], payload: dict[str, Any]) -> Any:
    """Resolve trigger.payload.<key> paths against the run's trigger_payload dict."""
    if parts[0] != "payload":
        return None
    cur: Any = payload
    for p in parts[1:]:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def _resolve_path(value: Any, parts: list[str]) -> Any:
    """Resolve nested dict/list path parts from an already-resolved base value."""
    cur: Any = value
    for p in parts:
        if isinstance(cur, dict):
            if p not in cur:
                return None
            cur = cur[p]
            continue
        if isinstance(cur, list):
            try:
                idx = int(p)
            except (TypeError, ValueError):
                return None
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
            continue
        return None
    return cur


def _resolve_target_schema_ref(ref: dict[str, Any], snapshot: dict[str, Any]) -> Any:
    """Resolve target_schema_ref to schema property field (e.g. options).
    data_target_id is optional; when absent, uses job target (snapshot.active_schema).
    """
    if not ref or not isinstance(ref, dict):
        return None
    prop_id = ref.get("schema_property_id")
    field_name = ref.get("field", "options")
    if not prop_id:
        return None
    # active_schema is always for job target; data_target_id in ref is legacy/optional
    active_schema = snapshot.get("active_schema") or {}
    props = active_schema.get("properties") or []
    for p in props:
        if p.get("id") == prop_id:
            return p.get(field_name)
    return None
