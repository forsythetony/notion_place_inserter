"""Resolve effective app limits: min(global, coalesce(user, global)) per dimension."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from loguru import logger

from app.domain.limits import AppLimits

_LIMIT_KEYS = (
    "max_stages_per_job",
    "max_pipelines_per_stage",
    "max_steps_per_pipeline",
    "max_jobs_per_owner",
    "max_triggers_per_owner",
    "max_runs_per_utc_day",
    "max_runs_per_utc_month",
)


class LimitsResolutionError(Exception):
    """Raised when global or merged configuration is incomplete for enforcement."""


def _json_hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def resolve_effective_app_limits(
    global_row: dict[str, Any],
    user_row: dict[str, Any] | None,
    *,
    owner_user_id: str,
    operation: str,
) -> AppLimits:
    """
    Compute effective ceilings: user_candidate = coalesce(user, global); effective = min(global, user_candidate).
    """
    intermediates: dict[str, dict[str, int]] = {}
    effective: dict[str, int] = {}

    for key in _LIMIT_KEYS:
        gv = global_row.get(key)
        uv = user_row.get(key) if user_row else None
        if gv is None:
            raise LimitsResolutionError(f"missing global limit: {key}")
        g_int = int(gv)
        configured_on_user = uv is not None
        candidate = int(uv) if uv is not None else g_int
        eff = min(g_int, candidate)
        intermediates[key] = {
            "global": g_int,
            "user_candidate": candidate,
            "user_configured": int(configured_on_user),
            "effective": eff,
        }
        effective[key] = eff

    logger.info(
        "effective_limits_resolved | owner_user_id={} operation={} global_hash={} user_hash={} detail={}",
        owner_user_id,
        operation,
        _json_hash({k: global_row.get(k) for k in _LIMIT_KEYS}),
        _json_hash({k: (user_row or {}).get(k) for k in _LIMIT_KEYS}),
        intermediates,
    )

    return AppLimits(
        max_stages_per_job=effective["max_stages_per_job"],
        max_pipelines_per_stage=effective["max_pipelines_per_stage"],
        max_steps_per_pipeline=effective["max_steps_per_pipeline"],
        max_jobs_per_owner=effective["max_jobs_per_owner"],
        max_triggers_per_owner=effective["max_triggers_per_owner"],
        max_runs_per_utc_day=effective["max_runs_per_utc_day"],
        max_runs_per_utc_month=effective["max_runs_per_utc_month"],
    )


def limits_resolution_summary(
    global_row: dict[str, Any],
    user_row: dict[str, Any] | None,
    effective: AppLimits,
) -> dict[str, Any]:
    """
    Metadata for admin UI: whether a per-user ``app_limits`` row exists and whether any
    effective cap is strictly below global (per-user stored value tightened the ceiling).
    """
    eff_map = {
        "max_stages_per_job": effective.max_stages_per_job,
        "max_pipelines_per_stage": effective.max_pipelines_per_stage,
        "max_steps_per_pipeline": effective.max_steps_per_pipeline,
        "max_jobs_per_owner": effective.max_jobs_per_owner,
        "max_triggers_per_owner": effective.max_triggers_per_owner,
        "max_runs_per_utc_day": effective.max_runs_per_utc_day,
        "max_runs_per_utc_month": effective.max_runs_per_utc_month,
    }
    dimensions_effective_below_global: list[str] = []
    for key in _LIMIT_KEYS:
        gv = global_row.get(key)
        if gv is None:
            continue
        if int(eff_map[key]) < int(gv):
            dimensions_effective_below_global.append(key)
    effective_matches_global_everywhere = all(
        int(eff_map[k]) == int(global_row[k]) for k in _LIMIT_KEYS
    )
    return {
        "has_user_stored_row": user_row is not None,
        "effective_matches_global_everywhere": effective_matches_global_everywhere,
        "dimensions_effective_below_global": dimensions_effective_below_global,
    }
