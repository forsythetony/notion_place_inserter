"""Tests for live-test snapshot scoping, cache fixtures, and destination-write skip."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.job_execution.job_execution_service import JobExecutionService
from app.services.job_execution.runtime_types import ExecutionContext
from app.services.pipeline_live_test.scoped_snapshot import (
    apply_cache_fixtures_to_ctx,
    apply_scope_to_snapshot,
)


def _minimal_snapshot(*, stage_ids: list[str], pipeline_ids: list[str], step_ids: list[str]) -> dict:
    stages = []
    for si, sid in enumerate(stage_ids):
        pipelines = []
        for pi, pid in enumerate(pipeline_ids):
            steps = []
            for ti, tid in enumerate(step_ids):
                steps.append(
                    {
                        "id": tid,
                        "step_template_id": "step_template_data_transform",
                        "display_name": tid,
                        "sequence": ti + 1,
                        "input_bindings": {},
                        "config": {},
                    }
                )
            pipelines.append(
                {
                    "id": pid,
                    "stage_id": sid,
                    "display_name": pid,
                    "sequence": pi + 1,
                    "step_ids": step_ids.copy(),
                    "steps": steps,
                }
            )
        stages.append(
            {
                "id": sid,
                "job_id": "job_1",
                "display_name": sid,
                "sequence": si + 1,
                "pipeline_ids": pipeline_ids.copy(),
                "pipelines": pipelines,
            }
        )
    return {
        "job": {
            "id": "job_1",
            "display_name": "Test",
            "target_id": "t1",
            "status": "active",
            "stage_ids": list(stage_ids),
            "stages": stages,
        },
        "target": {"id": "t1", "external_target_id": "ds-uuid"},
        "active_schema": {"properties": []},
    }


def test_apply_scope_stage_keeps_only_one_stage():
    snap = _minimal_snapshot(
        stage_ids=["s1", "s2"],
        pipeline_ids=["p1"],
        step_ids=["st1"],
    )
    # duplicate structure for s2
    snap["job"]["stages"][1]["pipelines"][0]["stage_id"] = "s2"
    out, boundary = apply_scope_to_snapshot(snap, "stage", stage_id="s1")
    assert len(out["job"]["stages"]) == 1
    assert out["job"]["stages"][0]["id"] == "s1"
    assert boundary is not None
    assert boundary["stage_ids"] == ["s1"]


def test_apply_scope_step_keeps_tail_steps():
    snap = _minimal_snapshot(
        stage_ids=["s1"],
        pipeline_ids=["p1"],
        step_ids=["a", "b", "c"],
    )
    out, boundary = apply_scope_to_snapshot(snap, "step", step_id="b")
    steps = out["job"]["stages"][0]["pipelines"][0]["steps"]
    ids = [s["id"] for s in steps]
    assert ids == ["b", "c"]
    assert boundary is not None
    assert set(boundary["step_ids"]) == {"b", "c"}


def test_apply_cache_fixtures_root_key():
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    apply_cache_fixtures_to_ctx(
        ctx,
        [{"cache_key": "k1", "path": None, "value": {"x": 1}}],
    )
    assert ctx.run_cache["k1"] == {"x": 1}


def test_execute_snapshot_run_skips_notion_when_disallowed():
    snap = _minimal_snapshot(stage_ids=["s1"], pipeline_ids=["p1"], step_ids=["st1"])
    # minimal step that does nothing destructive — use cache_set-like is complex;
    # use registry with a handler that returns empty — actually data_transform might need bindings.
    # Simplest: mock entire stage loop by snapshot with zero steps - but then no steps run.
    # Use one step template that exists and minimal: property_set would fail without allow - skip
    # Instead set stages empty and allow_destination_writes False - execute still hits create_page check
    snap["job"]["stages"][0]["pipelines"][0]["steps"] = []
    svc = JobExecutionService(
        notion_service=MagicMock(),
        claude_service=None,
        google_places_service=None,
        dry_run=False,
        run_repository=None,
        get_notion_token_fn=lambda _uid: None,
    )
    result = svc.execute_snapshot_run(
        snap,
        run_id="run1",
        job_id="platform1",
        trigger_payload={},
        owner_user_id=None,
        allow_destination_writes=False,
        invocation_source="editor_live_test",
    )
    assert result.get("destination_write_skipped") is True
    svc._notion.create_page.assert_not_called()


def test_scope_violation_raises():
    snap = _minimal_snapshot(stage_ids=["s1"], pipeline_ids=["p1"], step_ids=["st1"])
    # Put a step that will run
    svc = JobExecutionService(
        notion_service=MagicMock(),
        claude_service=MagicMock(),
        google_places_service=MagicMock(),
        dry_run=True,
        run_repository=None,
    )
    # Wrong step id in boundary triggers assert before handler
    boundary = {"stage_ids": ["s1"], "pipeline_ids": ["p1"], "step_ids": ["other"]}
    with pytest.raises(RuntimeError, match="Scope violation"):
        svc.execute_snapshot_run(
            snap,
            run_id="run1",
            job_id="pj",
            trigger_payload={"keywords": "x"},
            owner_user_id=None,
            allow_destination_writes=False,
            scope_boundary=boundary,
        )
