"""Snapshot-time cleanup for legacy trigger binding paths."""

from __future__ import annotations

from typing import Any

from app.services.trigger_request_body import (
    primary_string_field_for_legacy_mapping,
    request_body_schema_declares_field,
)

# Re-export for tests and older imports
__all__ = (
    "LEGACY_RAW_INPUT_REF",
    "legacy_raw_input_replacement_signal_ref",
    "migrate_raw_input_signal_refs_for_steps",
    "request_body_schema_declares_field",
)

LEGACY_RAW_INPUT_REF = "trigger.payload.raw_input"


def legacy_raw_input_replacement_signal_ref(triggers: list[Any]) -> str | None:
    """
    Single binding target when every trigger maps legacy ``raw_input`` to the same
    string field. Otherwise returns None (skip migration).
    """
    fields: list[str] = []
    for t in triggers:
        f = primary_string_field_for_legacy_mapping(getattr(t, "request_body_schema", None))
        if not f:
            return None
        fields.append(f)
    if len(set(fields)) != 1:
        return None
    return f"trigger.payload.{fields[0]}"


def migrate_raw_input_signal_refs_for_steps(
    steps: list[Any],
    replacement_signal_ref: str,
) -> int:
    """
    Rewrite ``trigger.payload.raw_input`` to ``replacement_signal_ref`` on step bindings.

    Mutates ``step.input_bindings`` in place. Returns number of bindings updated.
    """
    count = 0
    for step in steps:
        bindings = step.input_bindings
        if not bindings:
            continue
        new_bindings: dict[str, Any] = {}
        changed = False
        for name, binding in bindings.items():
            if (
                isinstance(binding, dict)
                and binding.get("signal_ref") == LEGACY_RAW_INPUT_REF
            ):
                new_bindings[name] = {**binding, "signal_ref": replacement_signal_ref}
                changed = True
                count += 1
            else:
                new_bindings[name] = binding
        if changed:
            step.input_bindings = new_bindings
    return count
