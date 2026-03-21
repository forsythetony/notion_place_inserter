"""Tests for trigger request body validation and trigger_payload construction."""

import pytest

from app.services.trigger_binding_migration import request_body_schema_declares_field
from app.services.trigger_request_body import (
    build_trigger_payload,
    debug_payload_json_for_logging,
    default_keywords_request_body_schema,
    management_body_fields_to_schema,
    validate_request_body_against_schema,
)


def test_build_trigger_payload_dual_writes_raw_input_for_primary_string():
    schema = default_keywords_request_body_schema()
    validated = validate_request_body_against_schema({"keywords": "  cafe  "}, schema)
    payload = build_trigger_payload(validated, schema)
    assert payload == {"keywords": "cafe", "raw_input": "cafe"}


def test_build_trigger_payload_empty_when_validation_empty():
    schema = {
        "type": "object",
        "properties": {"note": {"type": "string"}},
        "required": [],
    }
    payload = build_trigger_payload({}, schema)
    assert payload == {}
    assert "raw_input" not in payload


def test_validate_multi_field_body():
    schema = management_body_fields_to_schema(
        [
            {"name": "query", "type": "string", "required": True, "max_length": 100},
            {"name": "limit", "type": "number", "required": False},
        ]
    )
    v = validate_request_body_against_schema({"query": " pizza ", "limit": 5}, schema)
    assert v == {"query": "pizza", "limit": 5}
    p = build_trigger_payload(v, schema)
    assert p["query"] == "pizza"
    assert p["raw_input"] == "pizza"
    assert p["limit"] == 5


def test_validate_rejects_unknown_field():
    schema = default_keywords_request_body_schema()
    with pytest.raises(ValueError, match="Unknown field"):
        validate_request_body_against_schema({"keywords": "a", "extra": 1}, schema)


def test_request_body_schema_declares_keywords_json_schema():
    schema = {
        "type": "object",
        "properties": {"keywords": {"type": "string"}},
    }
    assert request_body_schema_declares_field(schema, "keywords")


def test_request_body_schema_declares_keywords_flat_map():
    assert request_body_schema_declares_field({"keywords": "string"}, "keywords")


def test_request_body_schema_declares_keywords_fields_envelope():
    assert request_body_schema_declares_field(
        {"fields": {"keywords": {"type": "string"}}},
        "keywords",
    )


def test_management_body_fields_rejects_empty():
    with pytest.raises(ValueError, match="At least one"):
        management_body_fields_to_schema([])


def test_debug_payload_json_for_logging_full_roundtrip():
    s = debug_payload_json_for_logging({"a": 1, "b": "x"})
    assert '"a": 1' in s and '"b": "x"' in s


def test_debug_payload_json_for_logging_respects_max_chars(monkeypatch):
    monkeypatch.setenv("WORKER_DEBUG_PAYLOAD_JSON_MAX_CHARS", "10")
    s = debug_payload_json_for_logging({"long": "abcdefghijklmnop"})
    assert "truncated" in s
    assert "total_len=" in s


def test_debug_payload_json_for_logging_truncates_strings_over_50_chars():
    import json

    long = "x" * 80
    s = debug_payload_json_for_logging({"image_b64": long, "nested": {"blob": long}})
    data = json.loads(s)
    assert data["image_b64"] == "x" * 47 + "..."
    assert len(data["image_b64"]) == 50
    assert data["nested"]["blob"] == data["image_b64"]
