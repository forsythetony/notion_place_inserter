"""Analyze test run configurations: fixtures, destination writes, external API call sites."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.services.pipeline_live_test.scoped_snapshot import apply_scope_to_snapshot

# step_template_id -> list of planned external call descriptors for editor UX / runtime overrides
_TEMPLATE_EXTERNAL_CALLS: dict[str, list[dict[str, Any]]] = {
    "step_template_optimize_input_claude": [
        {
            "call_site_id": "claude.optimize_input",
            "label": "Claude (optimize input)",
            "provider": "claude",
        }
    ],
    "step_template_google_places_lookup": [
        {
            "call_site_id": "google_places.lookup",
            "label": "Google Places (lookup)",
            "provider": "google_places",
        }
    ],
    "step_template_ai_constrain_values_claude": [
        {
            "call_site_id": "claude.ai_constrain_values",
            "label": "Claude (constrain values)",
            "provider": "claude",
        }
    ],
    "step_template_ai_prompt": [
        {
            "call_site_id": "claude.ai_prompt",
            "label": "Claude (AI prompt)",
            "provider": "claude",
        }
    ],
    "step_template_ai_select_relation": [
        {
            "call_site_id": "claude.ai_select_relation",
            "label": "Claude (select relation)",
            "provider": "claude",
        }
    ],
    "step_template_search_icons": [
        {
            "call_site_id": "freepik.search_icons",
            "label": "Freepik (search icons)",
            "provider": "freepik",
        }
    ],
    "step_template_upload_image_to_notion": [
        {
            "call_site_id": "notion.upload_image",
            "label": "Notion (upload image)",
            "provider": "notion",
        }
    ],
}

_DESTINATION_WRITE_TEMPLATES = frozenset(
    {
        "step_template_property_set",
        "step_template_upload_image_to_notion",
    }
)


def _flatten_steps(job_dict: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    out: list[tuple[str, str, dict[str, Any]]] = []
    stages = sorted(
        (s for s in (job_dict.get("stages") or []) if isinstance(s, dict) and s.get("id")),
        key=lambda s: s.get("sequence", 0),
    )
    for st in stages:
        sid = str(st.get("id", ""))
        pipes = sorted(
            (p for p in (st.get("pipelines") or []) if isinstance(p, dict) and p.get("id")),
            key=lambda p: p.get("sequence", 0),
        )
        for pipe in pipes:
            pid = str(pipe.get("id", ""))
            steps = sorted(
                (x for x in (pipe.get("steps") or []) if isinstance(x, dict) and x.get("id")),
                key=lambda x: x.get("sequence", 0),
            )
            for step in steps:
                out.append((sid, pid, step))
    return out


def _collect_dicts(obj: Any, sink: list[dict[str, Any]]) -> None:
    if isinstance(obj, dict):
        sink.append(obj)
        for v in obj.values():
            _collect_dicts(v, sink)
    elif isinstance(obj, list):
        for v in obj:
            _collect_dicts(v, sink)


def _binding_dicts_for_step(step: dict[str, Any]) -> list[dict[str, Any]]:
    sink: list[dict[str, Any]] = []
    ib = step.get("input_bindings") or {}
    for v in ib.values():
        if isinstance(v, dict):
            sink.append(v)
    _collect_dicts(step.get("config") or {}, sink)
    return sink


def _fixture_cache_keys(fixtures: dict[str, Any] | None) -> set[str]:
    keys: set[str] = set()
    if not fixtures or not isinstance(fixtures, dict):
        return keys
    for e in fixtures.get("cache_entries") or []:
        if isinstance(e, dict) and e.get("cache_key"):
            keys.add(str(e["cache_key"]))
    return keys


def analyze_live_test(
    full_snapshot: dict[str, Any],
    *,
    scope_kind: str,
    stage_id: str | None = None,
    pipeline_id: str | None = None,
    step_id: str | None = None,
    fixtures: dict[str, Any] | None = None,
    api_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Return analysis: unsatisfied requirements, destination_write_blocked, planned_external_calls.

    ``api_overrides`` keys are ``call_site_id`` -> ``{"enabled": bool, "manual_response": ...}``.
    Disabled sites without ``manual_response`` yield ``unsatisfied_api_fixtures``.
    """
    api_overrides = api_overrides or {}
    fixtures = fixtures or {}
    dest_blocked = False
    if scope_kind != "job":
        scoped, _b = apply_scope_to_snapshot(
            full_snapshot,
            scope_kind,
            stage_id=stage_id,
            pipeline_id=pipeline_id,
            step_id=step_id,
        )
        job_dict = scoped.get("job") or {}
    else:
        job_dict = deepcopy(full_snapshot.get("job") or {})

    steps_order = _flatten_steps(job_dict)
    step_ids_in_scope = {s[2].get("id") for s in steps_order if s[2].get("id")}
    keys_from_fixtures = _fixture_cache_keys(fixtures)
    keys_written: set[str] = set(keys_from_fixtures)
    steps_completed: set[str] = set()

    unsatisfied: list[dict[str, Any]] = []

    for stg_id, pipe_id, step in steps_order:
        tid = step.get("step_template_id") or ""
        sid = step.get("id") or ""

        if scope_kind != "job" and tid in _DESTINATION_WRITE_TEMPLATES:
            dest_blocked = True

        for d in _binding_dicts_for_step(step):
            if "signal_ref" in d and isinstance(d["signal_ref"], str):
                ref = d["signal_ref"]
                parts = ref.split(".")
                if len(parts) >= 3 and parts[0] == "step":
                    dep_step = parts[1]
                    if dep_step not in steps_completed and dep_step not in step_ids_in_scope:
                        unsatisfied.append(
                            {
                                "requirement_id": f"sig_{sid}_{dep_step}",
                                "kind": "signal_ref",
                                "signal_ref": ref,
                                "step_id": sid,
                                "message": f"Step {sid!r} depends on output of step {dep_step!r} outside this scope",
                            }
                        )
                    elif dep_step in step_ids_in_scope and dep_step not in steps_completed:
                        unsatisfied.append(
                            {
                                "requirement_id": f"sig_order_{sid}_{dep_step}",
                                "kind": "signal_ref",
                                "signal_ref": ref,
                                "step_id": sid,
                                "message": f"Step {sid!r} references step {dep_step!r} before it runs (ordering)",
                            }
                        )
            if "cache_key_ref" in d and isinstance(d["cache_key_ref"], dict):
                ref = d["cache_key_ref"]
                ck = ref.get("cache_key")
                if ck and str(ck) not in keys_written:
                    unsatisfied.append(
                        {
                            "requirement_id": f"cache_{sid}_{ck}",
                            "kind": "cache_key_ref",
                            "cache_key_ref": {"cache_key": ck, "path": ref.get("path")},
                            "step_id": sid,
                            "message": f"Cache key {ck!r} is required before step {sid!r} runs",
                        }
                    )

        if tid == "step_template_cache_set":
            ck = (step.get("config") or {}).get("cache_key")
            if ck:
                keys_written.add(str(ck))
        steps_completed.add(str(sid))

    planned_calls: list[dict[str, Any]] = []
    for stg_id, pipe_id, step in steps_order:
        tid = step.get("step_template_id") or ""
        sid = step.get("id") or ""
        for call in _TEMPLATE_EXTERNAL_CALLS.get(tid, ()):
            row = {
                **deepcopy(call),
                "step_id": sid,
                "stage_id": stg_id,
                "pipeline_id": pipe_id,
            }
            planned_calls.append(row)

    unsatisfied_api: list[dict[str, Any]] = []
    for call in planned_calls:
        csid = call.get("call_site_id")
        if not csid:
            continue
        ov = api_overrides.get(csid) or {}
        if isinstance(ov, dict) and ov.get("enabled") is False:
            if "manual_response" not in ov:
                unsatisfied_api.append(
                    {
                        "requirement_id": f"api_manual_{csid}",
                        "kind": "api_manual_response",
                        "call_site_id": csid,
                        "step_id": call.get("step_id"),
                        "message": f"Call site {csid!r} is disabled; provide manual_response",
                    }
                )

    merged_unsat = unsatisfied + unsatisfied_api
    return {
        "ok": len(merged_unsat) == 0 and not dest_blocked,
        "destination_write_blocked": dest_blocked,
        "unsatisfied_requirements": merged_unsat,
        "planned_external_calls": planned_calls,
    }


def analyzer_payload_hash(analysis: dict[str, Any]) -> str:
    """Short stable fingerprint for run metadata (not cryptographic)."""
    blob = json.dumps(analysis, sort_keys=True, default=str)
    return f"sha1:{hash(blob) & 0xFFFFFFFF:08x}"
