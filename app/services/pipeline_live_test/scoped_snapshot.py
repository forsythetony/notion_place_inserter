"""Filter resolved job snapshots to a test-run scope; seed run cache from fixtures."""

from __future__ import annotations

import copy
from typing import Any

from loguru import logger

from app.services.job_execution.runtime_types import ExecutionContext

_SCOPE_KINDS = frozenset({"job", "stage", "pipeline", "step"})


def apply_cache_fixtures_to_ctx(
    ctx: ExecutionContext,
    cache_entries: list[dict[str, Any]] | None,
) -> None:
    """
    Merge live-test cache fixtures into ctx.run_cache.

    Each entry: ``{"cache_key": str, "path": str | None, "value": Any}``.
    When ``path`` is None, sets ``run_cache[cache_key] = value``.
    When ``path`` is a dotted path, merges into a dict at ``cache_key`` (v1: shallow set on last segment).
    """
    if not cache_entries:
        return
    for entry in cache_entries:
        if not isinstance(entry, dict):
            continue
        key = entry.get("cache_key")
        if not key or not isinstance(key, str):
            continue
        value = entry.get("value")
        path = entry.get("path")
        if not path:
            ctx.run_cache[key] = copy.deepcopy(value)
            continue
        if not isinstance(path, str):
            ctx.run_cache[key] = copy.deepcopy(value)
            continue
        parts = [p for p in path.split(".") if p]
        if not parts:
            ctx.run_cache[key] = copy.deepcopy(value)
            continue
        root = ctx.run_cache.get(key)
        if not isinstance(root, dict):
            root = {}
        cur: dict[str, Any] = root
        for p in parts[:-1]:
            nxt = cur.get(p)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[p] = nxt
            cur = nxt
        cur[parts[-1]] = copy.deepcopy(value)
        ctx.run_cache[key] = root


def _find_step_location(
    stages: list[dict[str, Any]], step_id: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], int] | None:
    """Return (stage, pipeline, step_dict, step_index_in_pipeline) or None."""
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        for pipeline in stage.get("pipelines") or []:
            if not isinstance(pipeline, dict):
                continue
            steps = [
                s for s in (pipeline.get("steps") or []) if isinstance(s, dict) and s.get("id")
            ]
            steps_sorted = sorted(steps, key=lambda s: s.get("sequence", 0))
            for idx, step in enumerate(steps_sorted):
                if step.get("id") == step_id:
                    return stage, pipeline, step, idx
    return None


def apply_scope_to_snapshot(
    snapshot: dict[str, Any],
    scope_kind: str,
    *,
    stage_id: str | None = None,
    pipeline_id: str | None = None,
    step_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """
    Return a deep copy of ``snapshot`` with ``job.stages`` reduced to the requested scope.

    Also returns ``scope_boundary`` dict with keys ``stage_ids``, ``pipeline_ids``, ``step_ids``
    (lists of str) for JobExecutionService assertions, or ``None`` when ``scope_kind == job``.

    **Step scope (Option B):** keep the selected step and all following steps in the same inner pipeline.
    """
    if scope_kind not in _SCOPE_KINDS:
        raise ValueError(f"Invalid scope_kind: {scope_kind!r}")

    out = copy.deepcopy(snapshot)
    job = out.get("job")
    if not isinstance(job, dict):
        raise ValueError("Snapshot missing job dict")

    stages = [s for s in (job.get("stages") or []) if isinstance(s, dict) and s.get("id")]
    if not stages:
        job["stages"] = []
        job["stage_ids"] = []
        return out, None if scope_kind == "job" else {"stage_ids": [], "pipeline_ids": [], "step_ids": []}

    if scope_kind == "job":
        return out, None

    if scope_kind == "stage":
        if not stage_id:
            raise ValueError("stage_id required for scope_kind=stage")
        filtered = [copy.deepcopy(s) for s in stages if s.get("id") == stage_id]
        if not filtered:
            raise ValueError(f"stage_id not found: {stage_id!r}")
        job["stages"] = filtered
        job["stage_ids"] = [stage_id]
        boundary = _boundary_from_stages(filtered)
        return out, boundary

    if scope_kind == "pipeline":
        if not pipeline_id:
            raise ValueError("pipeline_id required for scope_kind=pipeline")
        for st in stages:
            pipes = [p for p in (st.get("pipelines") or []) if isinstance(p, dict) and p.get("id")]
            for pipe in pipes:
                if pipe.get("id") == pipeline_id:
                    st_copy = copy.deepcopy(st)
                    st_copy["pipelines"] = [copy.deepcopy(pipe)]
                    st_copy["pipeline_ids"] = [pipeline_id]
                    job["stages"] = [st_copy]
                    job["stage_ids"] = [st.get("id", "")]
                    boundary = _boundary_from_stages(job["stages"])
                    return out, boundary
        raise ValueError(f"pipeline_id not found: {pipeline_id!r}")

    # step
    if not step_id:
        raise ValueError("step_id required for scope_kind=step")
    loc = _find_step_location(stages, step_id)
    if loc is None:
        raise ValueError(f"step_id not found: {step_id!r}")
    stage, pipeline, _step0, idx = loc
    pipes = [p for p in (stage.get("pipelines") or []) if isinstance(p, dict) and p.get("id")]
    pipe = next((p for p in pipes if p.get("id") == pipeline.get("id")), None)
    if pipe is None:
        raise ValueError("pipeline resolution failed for step scope")
    steps_all = [s for s in (pipe.get("steps") or []) if isinstance(s, dict) and s.get("id")]
    steps_sorted = sorted(steps_all, key=lambda s: s.get("sequence", 0))
    kept = steps_sorted[idx:]
    stage_copy = copy.deepcopy(stage)
    for p in stage_copy.get("pipelines") or []:
        if not isinstance(p, dict) or p.get("id") != pipeline.get("id"):
            continue
        p["steps"] = kept
        p["step_ids"] = [s.get("id") for s in kept if s.get("id")]
        break
    stage_copy["pipelines"] = [p for p in stage_copy["pipelines"] if isinstance(p, dict) and p.get("id") == pipeline.get("id")]
    if stage_copy.get("pipeline_ids"):
        stage_copy["pipeline_ids"] = [pipeline.get("id", "")]
    job["stages"] = [stage_copy]
    job["stage_ids"] = [stage.get("id", "")]
    boundary = _boundary_from_stages(job["stages"])
    logger.debug(
        "pipeline_live_test_scope_step | stage_id={} pipeline_id={} step_id={} kept_steps={}",
        stage.get("id"),
        pipeline.get("id"),
        step_id,
        boundary.get("step_ids"),
    )
    return out, boundary


def _boundary_from_stages(stages: list[dict[str, Any]]) -> dict[str, Any]:
    stage_ids: list[str] = []
    pipeline_ids: list[str] = []
    step_ids: list[str] = []
    for st in stages:
        if not isinstance(st, dict):
            continue
        sid = st.get("id")
        if sid:
            stage_ids.append(str(sid))
        for p in st.get("pipelines") or []:
            if not isinstance(p, dict):
                continue
            pid = p.get("id")
            if pid:
                pipeline_ids.append(str(pid))
            for s in p.get("steps") or []:
                if isinstance(s, dict) and s.get("id"):
                    step_ids.append(str(s["id"]))
    return {
        "stage_ids": stage_ids,
        "pipeline_ids": pipeline_ids,
        "step_ids": step_ids,
    }
