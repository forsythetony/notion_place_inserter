"""
Validate HTTP trigger POST bodies against ``request_body_schema`` and build ``trigger_payload``.

Supports JSON Schema-style objects, a flat map of ``field_name -> "string"``, and v1
``fields`` envelopes. Trigger payload keys match validated body keys; optional legacy
``raw_input`` duplicates the chosen primary string field for migration compatibility.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

_DEPRECATION_LOGGED = False


def _log_raw_input_deprecation_once() -> None:
    global _DEPRECATION_LOGGED
    if _DEPRECATION_LOGGED:
        return
    _DEPRECATION_LOGGED = True
    logger.warning(
        "trigger_payload_deprecation | raw_input is deprecated; bind using "
        "trigger.payload.<field> from the trigger request_body_schema. "
        "raw_input is still duplicated for compatibility during the migration window."
    )


def _properties_and_required(schema: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Normalize stored schema into (properties_spec, required_field_names).

    ``properties_spec`` maps field name -> JSON-schema-like field spec (at least ``type``).
    """
    if not schema or not isinstance(schema, dict):
        return {}, []

    if "properties" in schema and isinstance(schema["properties"], dict):
        req = schema.get("required")
        required_list: list[str] = (
            list(req) if isinstance(req, list) else []
        )
        return dict(schema["properties"]), required_list

    fields = schema.get("fields")
    if isinstance(fields, dict):
        props: dict[str, Any] = {}
        required_list = []
        for name, spec in fields.items():
            if not isinstance(spec, dict):
                continue
            t = spec.get("type", "string")
            props[name] = {"type": t, **{k: v for k, v in spec.items() if k != "type"}}
            if spec.get("required", True):
                required_list.append(name)
        return props, required_list

    # Flat map: {"keywords": "string", "limit": "number"}
    props = {}
    required_list = []
    reserved = frozenset({"type", "required", "properties", "fields", "schema_version"})
    for key, val in schema.items():
        if key in reserved:
            continue
        if val == "string":
            props[key] = {"type": "string"}
            required_list.append(key)
        elif val == "number":
            props[key] = {"type": "number"}
            required_list.append(key)
        elif val == "boolean":
            props[key] = {"type": "boolean"}
            required_list.append(key)
        elif isinstance(val, dict) and "type" in val:
            props[key] = val
            required_list.append(key)
    return props, required_list


def list_request_body_field_names(schema: dict[str, Any] | None) -> list[str]:
    """Ordered field names from schema (properties / fields / flat map)."""
    props, _ = _properties_and_required(schema or {})
    return list(props.keys())


def primary_string_field_for_legacy_mapping(schema: dict[str, Any] | None) -> str | None:
    """
    Which body field should receive migrations from ``trigger.payload.raw_input`` and
    supply the legacy ``raw_input`` duplicate — first required string field, else first
    string property in declaration order.
    """
    props, required_list = _properties_and_required(schema or {})
    if not props:
        return None
    for name in required_list:
        spec = props.get(name) or {}
        if spec.get("type") == "string":
            return name
    for name in props:
        spec = props.get(name) or {}
        if spec.get("type") == "string":
            return name
    return None


def request_body_schema_declares_field(schema: dict[str, Any] | None, field: str) -> bool:
    """True if ``field`` is a defined body property."""
    props, _ = _properties_and_required(schema or {})
    return field in props


def validate_request_body_against_schema(
    body: dict[str, Any],
    schema: dict[str, Any] | None,
    *,
    unknown_fields: str = "reject",
) -> dict[str, Any]:
    """
    Validate ``body`` and return a normalized flat dict for ``trigger_payload``.

    ``unknown_fields``: ``reject`` (default) or ``ignore`` for forward compatibility.
    Raises ``ValueError`` with a human-readable message on failure.
    """
    if schema is None or not isinstance(schema, dict):
        raise ValueError("Trigger has no request_body_schema; configure one for this trigger.")

    props, required_list = _properties_and_required(schema)
    if not props:
        raise ValueError("request_body_schema defines no fields; add at least one property.")

    if unknown_fields == "reject":
        for key in body:
            if key not in props:
                raise ValueError(f"Unknown field '{key}' in request body.")

    result: dict[str, Any] = {}
    for name, spec in props.items():
        if name not in body:
            if name in required_list:
                raise ValueError(f"Missing required field: '{name}'")
            continue
        val = body[name]
        ftype = spec.get("type", "string")

        if ftype == "string":
            if val is None:
                raise ValueError(f"Field '{name}' must be a string.")
            if not isinstance(val, str):
                raise ValueError(f"Field '{name}' must be a string.")
            s = val.strip()
            min_len = int(spec.get("minLength", 0) or 0)
            if min_len > 0 and len(s) < min_len:
                raise ValueError(f"Field '{name}' cannot be empty.")
            max_len = spec.get("maxLength")
            if max_len is not None and len(val) > int(max_len):
                raise ValueError(
                    f"Field '{name}' must be at most {int(max_len)} characters."
                )
            result[name] = s
        elif ftype == "number":
            if val is None or isinstance(val, bool):
                raise ValueError(f"Field '{name}' must be a number.")
            if isinstance(val, (int, float)):
                result[name] = val
            elif isinstance(val, str):
                try:
                    if "." in val:
                        result[name] = float(val)
                    else:
                        result[name] = int(val, 10)
                except ValueError as e:
                    raise ValueError(f"Field '{name}' must be a number.") from e
            else:
                raise ValueError(f"Field '{name}' must be a number.")
        elif ftype == "boolean":
            if isinstance(val, bool):
                result[name] = val
            elif val in (0, 1, "0", "1", "true", "false"):
                result[name] = val in (True, 1, "1", "true")
            else:
                raise ValueError(f"Field '{name}' must be a boolean.")
        else:
            raise ValueError(f"Unsupported type for field '{name}': {ftype}")

    return result


def build_trigger_payload(
    validated_body: dict[str, Any],
    schema: dict[str, Any] | None,
    *,
    include_legacy_raw_input: bool = True,
) -> dict[str, Any]:
    """
    Build ``trigger_payload`` from an already-validated body.

    When ``include_legacy_raw_input`` and schema defines a primary string field, adds
    ``raw_input`` with the same value for legacy bindings.
    """
    payload = dict(validated_body)
    if not include_legacy_raw_input or "raw_input" in payload:
        return payload
    primary = primary_string_field_for_legacy_mapping(schema)
    if primary and primary in payload and isinstance(payload[primary], str):
        _log_raw_input_deprecation_once()
        payload = {**payload, "raw_input": payload[primary]}
    return payload


def default_keywords_request_body_schema() -> dict[str, Any]:
    """Default JSON Schema for location-style triggers (backward compatible)."""
    return {
        "type": "object",
        "required": ["keywords"],
        "properties": {
            "keywords": {
                "type": "string",
                "minLength": 1,
                "maxLength": 300,
            },
        },
    }


def management_body_fields_to_schema(fields: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Convert UI/API ``body_fields`` list into a JSON Schema document.

    Each item: ``name``, ``type`` (``string`` | ``number`` | ``boolean``), ``required`` (bool),
    optional ``max_length`` for strings.
    """
    properties: dict[str, Any] = {}
    required: list[str] = []
    for f in fields:
        name = (f.get("name") or "").strip()
        if not name:
            raise ValueError("Each body field must have a non-empty name.")
        ftype = f.get("type", "string")
        if ftype not in ("string", "number", "boolean"):
            raise ValueError(f"Unsupported field type for '{name}': {ftype}")
        is_required = f.get("required", True)
        spec: dict[str, Any] = {"type": ftype}
        if ftype == "string":
            max_len = f.get("max_length")
            if max_len is not None:
                spec["maxLength"] = int(max_len)
            if f.get("min_length") is not None:
                spec["minLength"] = int(f["min_length"])
            elif is_required:
                spec["minLength"] = 1
        prop = spec
        properties[name] = prop
        if is_required:
            required.append(name)
    if not properties:
        raise ValueError("At least one body field is required.")
    return {
        "type": "object",
        "required": required,
        "properties": properties,
    }


def preview_string_for_log(payload: dict[str, Any], max_len: int = 50) -> str:
    """Short preview for logging (first string value found)."""
    for v in payload.values():
        if isinstance(v, str) and v.strip():
            s = v.strip()
            return s[: max_len - 3] + "..." if len(s) > max_len else s
    return ""
