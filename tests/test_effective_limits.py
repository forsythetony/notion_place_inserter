"""Tests for effective app limits resolution."""

import pytest

from app.domain.limits import AppLimits
from app.services.effective_limits import (
    LimitsResolutionError,
    limits_resolution_summary,
    resolve_effective_app_limits,
)


def _global_row():
    return {
        "max_stages_per_job": 10,
        "max_pipelines_per_stage": 10,
        "max_steps_per_pipeline": 20,
        "max_jobs_per_owner": 100,
        "max_triggers_per_owner": 50,
        "max_runs_per_utc_day": 500,
        "max_runs_per_utc_month": 10000,
    }


def test_resolve_min_global_when_user_higher():
    user = {
        "max_stages_per_job": 50,
        "max_pipelines_per_stage": None,
        "max_steps_per_pipeline": None,
        "max_jobs_per_owner": None,
        "max_triggers_per_owner": None,
        "max_runs_per_utc_day": None,
        "max_runs_per_utc_month": None,
    }
    eff = resolve_effective_app_limits(
        _global_row(),
        user,
        owner_user_id="u1",
        operation="test",
    )
    assert eff.max_stages_per_job == 10
    assert eff.max_jobs_per_owner == 100


def test_resolve_user_lower_than_global():
    user = {
        "max_stages_per_job": 5,
        "max_pipelines_per_stage": 10,
        "max_steps_per_pipeline": 20,
        "max_jobs_per_owner": 100,
        "max_triggers_per_owner": 50,
        "max_runs_per_utc_day": 500,
        "max_runs_per_utc_month": 10000,
    }
    eff = resolve_effective_app_limits(
        _global_row(),
        user,
        owner_user_id="u1",
        operation="test",
    )
    assert eff.max_stages_per_job == 5


def test_resolve_missing_global_raises():
    g = dict(_global_row())
    g["max_jobs_per_owner"] = None
    with pytest.raises(LimitsResolutionError):
        resolve_effective_app_limits(g, None, owner_user_id="u1", operation="test")


def test_resolve_returns_applimits():
    eff = resolve_effective_app_limits(
        _global_row(),
        None,
        owner_user_id="u1",
        operation="test",
    )
    assert isinstance(eff, AppLimits)


def test_limits_resolution_summary_no_user_row():
    eff = resolve_effective_app_limits(
        _global_row(),
        None,
        owner_user_id="u1",
        operation="test",
    )
    s = limits_resolution_summary(_global_row(), None, eff)
    assert s["has_user_stored_row"] is False
    assert s["effective_matches_global_everywhere"] is True
    assert s["dimensions_effective_below_global"] == []


def test_limits_resolution_summary_user_tightens():
    user = {
        "max_stages_per_job": 5,
        "max_pipelines_per_stage": 10,
        "max_steps_per_pipeline": 20,
        "max_jobs_per_owner": 100,
        "max_triggers_per_owner": 50,
        "max_runs_per_utc_day": 500,
        "max_runs_per_utc_month": 10000,
    }
    eff = resolve_effective_app_limits(
        _global_row(),
        user,
        owner_user_id="u1",
        operation="test",
    )
    s = limits_resolution_summary(_global_row(), user, eff)
    assert s["has_user_stored_row"] is True
    assert s["effective_matches_global_everywhere"] is False
    assert s["dimensions_effective_below_global"] == ["max_stages_per_job"]
