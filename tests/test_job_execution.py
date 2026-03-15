"""Unit tests for snapshot-driven job execution (p3_pr06)."""

from unittest.mock import MagicMock

import pytest

from app.services.job_execution.binding_resolver import resolve_binding, resolve_input_bindings
from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.handlers import (
    CacheGetHandler,
    CacheSetHandler,
    OptimizeInputClaudeHandler,
    PropertySetHandler,
)
from app.services.job_execution.step_runtime_registry import StepRuntimeRegistry
from app.services.job_execution.target_write_adapter import build_notion_properties_payload


def test_resolve_signal_ref_trigger_payload():
    """signal_ref trigger.payload.raw_input resolves from trigger_payload."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={"raw_input": "coffee shop"},
    )
    result = resolve_binding(
        {"signal_ref": "trigger.payload.raw_input"},
        ctx,
        {},
    )
    assert result == "coffee shop"


def test_resolve_signal_ref_step_output():
    """signal_ref step.step_id.output_name resolves from step_outputs."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    ctx.set_step_output("step_optimize_query", "optimized_query", "Stone Arch Bridge Minneapolis")
    result = resolve_binding(
        {"signal_ref": "step.step_optimize_query.optimized_query"},
        ctx,
        {},
    )
    assert result == "Stone Arch Bridge Minneapolis"


def test_resolve_cache_key():
    """cache_key in binding reads from run_cache."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    ctx.run_cache["google_places_response"] = {"places": []}
    result = resolve_binding(
        {"cache_key": "google_places_response"},
        ctx,
        {},
    )
    assert result == {"places": []}


def test_resolve_static_value():
    """static_value returns literal."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    result = resolve_binding({"static_value": "literal"}, ctx, {})
    assert result == "literal"


def test_resolve_target_schema_ref_options():
    """target_schema_ref resolves schema property options."""
    snapshot = {
        "active_schema": {
            "properties": [
                {
                    "id": "prop_tags",
                    "external_property_id": "tags",
                    "options": [
                        {"id": "opt1", "name": "History"},
                        {"id": "opt2", "name": "Landmark"},
                    ],
                },
            ],
        },
    }
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    result = resolve_binding(
        {
            "target_schema_ref": {
                "data_target_id": "t1",
                "schema_property_id": "prop_tags",
                "field": "options",
            },
        },
        ctx,
        snapshot,
    )
    assert result == [{"id": "opt1", "name": "History"}, {"id": "opt2", "name": "Landmark"}]


def test_resolve_input_bindings_multiple():
    """resolve_input_bindings resolves all bindings."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={"raw_input": "pizza"},
    )
    ctx.set_step_output("step_a", "value", "resolved")
    bindings = {
        "query": {"signal_ref": "trigger.payload.raw_input"},
        "other": {"signal_ref": "step.step_a.value"},
    }
    result = resolve_input_bindings(bindings, ctx, {})
    assert result["query"] == "pizza"
    assert result["other"] == "resolved"


def test_cache_set_handler_stores_in_run_cache():
    """CacheSetHandler stores value in run_cache."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = CacheSetHandler()
    handler.execute(
        step_id="step_cache",
        config={"cache_key": "my_key"},
        input_bindings={"value": {"signal_ref": "trigger.payload.raw_input"}},
        resolved_inputs={"value": "stored_value"},
        ctx=ctx,
        snapshot={},
    )
    assert ctx.run_cache.get("my_key") == "stored_value"


def test_cache_get_handler_returns_cached_value():
    """CacheGetHandler returns value from run_cache."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx.run_cache["my_key"] = "cached"
    handler = CacheGetHandler()
    result = handler.execute(
        step_id="step_get",
        config={"cache_key": "my_key"},
        input_bindings={},
        resolved_inputs={},
        ctx=ctx,
        snapshot={},
    )
    assert result == {"value": "cached"}


def test_property_set_handler_stores_in_properties():
    """PropertySetHandler stores value in ctx.properties."""
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    handler = PropertySetHandler()
    handler.execute(
        step_id="step_prop",
        config={"schema_property_id": "prop_tags"},
        input_bindings={"value": {}},
        resolved_inputs={"value": ["History", "Landmark"]},
        ctx=ctx,
        snapshot={},
    )
    assert ctx.properties.get("prop_tags") == ["History", "Landmark"]


def test_optimize_input_claude_handler_returns_optimized_query():
    """OptimizeInputClaudeHandler returns optimized_query (or passthrough when no Claude)."""
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    handler = OptimizeInputClaudeHandler()
    result = handler.execute(
        step_id="step_opt",
        config={"prompt": "Rewrite"},
        input_bindings={"query": {}},
        resolved_inputs={"query": "coffee shop"},
        ctx=ctx,
        snapshot={},
    )
    assert "optimized_query" in result
    assert result["optimized_query"] == "coffee shop"  # no Claude, passthrough


def test_step_runtime_registry_get_returns_handler():
    """StepRuntimeRegistry returns handler for registered step_template_id."""
    from app.services.job_execution.handlers import CacheSetHandler

    reg = StepRuntimeRegistry()
    reg.register("step_template_cache_set", CacheSetHandler)
    handler = reg.get("step_template_cache_set")
    assert handler is not None
    assert isinstance(handler, CacheSetHandler)


def test_step_runtime_registry_get_unknown_returns_none():
    """StepRuntimeRegistry returns None for unknown step_template_id."""
    reg = StepRuntimeRegistry()
    assert reg.get("step_template_unknown") is None


def test_build_notion_properties_payload_multi_select():
    """build_notion_properties_payload formats multi_select from list."""
    ctx_properties = {"prop_tags": ["History", "Landmark"]}
    active_schema = {
        "properties": [
            {
                "id": "prop_tags",
                "external_property_id": "tags",
                "property_type": "multi_select",
                "options": [{"id": "o1", "name": "History"}, {"id": "o2", "name": "Landmark"}],
            },
        ],
    }
    result = build_notion_properties_payload(ctx_properties, active_schema)
    assert "tags" in result
    assert result["tags"]["multi_select"] == [{"name": "History"}, {"name": "Landmark"}]
