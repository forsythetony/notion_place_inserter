"""Clone a JobGraph with new prefixed stage/pipeline/step ids (avoids colliding with bootstrap ids)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.domain.jobs import JobDefinition
from app.services.validation_service import JobGraph


def _remap_signal_ref(value: str, id_map: dict[str, str]) -> str:
    if not value.startswith("step."):
        return value
    rest = value[len("step.") :]
    dot = rest.find(".")
    if dot == -1:
        return value
    step_id, tail = rest[:dot], rest[dot:]
    new_sid = id_map.get(step_id)
    if new_sid is None:
        return value
    return f"step.{new_sid}{tail}"


def _rewrite_nested(obj: Any, id_map: dict[str, str]) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k == "signal_ref" and isinstance(v, str):
                out[k] = _remap_signal_ref(v, id_map)
            elif k == "linked_step_id" and isinstance(v, str):
                out[k] = id_map.get(v, v)
            elif isinstance(v, (dict, list)):
                out[k] = _rewrite_nested(v, id_map)
            elif isinstance(v, str) and v in id_map:
                out[k] = id_map[v]
            else:
                out[k] = v
        return out
    if isinstance(obj, list):
        return [_rewrite_nested(x, id_map) for x in obj]
    if isinstance(obj, str) and obj in id_map:
        return id_map[obj]
    return obj


def clone_job_graph_with_prefixed_ids(
    graph: JobGraph,
    new_job_id: str,
    *,
    owner_user_id: str,
    display_name: str,
    target_id: str | None = None,
) -> JobGraph:
    """
    Produce a copy of graph where job id is ``new_job_id`` and every stage, pipeline,
    and step id is prefixed as ``{new_job_id}_{old_id}``, with bindings updated to match.
    """
    id_map: dict[str, str] = {}
    for s in graph.stages:
        id_map[s.id] = f"{new_job_id}_{s.id}"
    for p in graph.pipelines:
        id_map[p.id] = f"{new_job_id}_{p.id}"
    for st in graph.steps:
        id_map[st.id] = f"{new_job_id}_{st.id}"

    tid = target_id if target_id is not None else graph.job.target_id

    job = JobDefinition(
        id=new_job_id,
        owner_user_id=owner_user_id,
        display_name=display_name,
        target_id=tid,
        status=graph.job.status,
        stage_ids=[id_map[sid] for sid in graph.job.stage_ids],
        workspace_id=graph.job.workspace_id,
        visibility=graph.job.visibility,
        default_run_settings=graph.job.default_run_settings,
        created_at=graph.job.created_at,
        updated_at=graph.job.updated_at,
    )

    stages = [
        replace(
            s,
            id=id_map[s.id],
            job_id=new_job_id,
            pipeline_ids=[id_map[pid] for pid in s.pipeline_ids],
        )
        for s in graph.stages
    ]
    pipelines = [
        replace(
            p,
            id=id_map[p.id],
            stage_id=id_map[p.stage_id],
            step_ids=[id_map[sid] for sid in p.step_ids],
        )
        for p in graph.pipelines
    ]
    steps = [
        replace(
            st,
            id=id_map[st.id],
            pipeline_id=id_map[st.pipeline_id],
            input_bindings=_rewrite_nested(st.input_bindings, id_map),
            config=_rewrite_nested(st.config, id_map),
        )
        for st in graph.steps
    ]

    return JobGraph(job=job, stages=stages, pipelines=pipelines, steps=steps)
