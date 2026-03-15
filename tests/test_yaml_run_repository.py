"""Tests for YamlRunRepository."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.domain.runs import (
    JobRun,
    PipelineRun,
    StageRun,
    StepRun,
    UsageRecord,
)
from app.repositories.yaml_run_repository import YamlRunRepository


@pytest.fixture
def temp_repo():
    """YamlRunRepository with temp directory."""
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        Path(base).mkdir(parents=True)
        Path(base, "tenants", "owner1").mkdir(parents=True)
        yield YamlRunRepository(base=base)


def test_save_and_get_job_run(temp_repo):
    """save_job_run persists and get_job_run retrieves."""
    run = JobRun(
        id="run-1",
        owner_user_id="owner1",
        job_id="job-1",
        trigger_id="trigger-1",
        target_id="target-1",
        status="succeeded",
        trigger_payload={"raw_input": "park"},
        definition_snapshot_ref="snap-1",
        platform_job_id="loc_abc",
        retry_count=0,
    )
    temp_repo.save_job_run(run)
    loaded = temp_repo.get_job_run("run-1", "owner1")
    assert loaded is not None
    assert loaded.id == "run-1"
    assert loaded.status == "succeeded"
    assert loaded.trigger_payload == {"raw_input": "park"}
    assert loaded.definition_snapshot_ref == "snap-1"
    assert loaded.platform_job_id == "loc_abc"


def test_get_job_run_by_platform_job_id(temp_repo):
    """get_job_run_by_platform_job_id finds run by platform_job_id."""
    run = JobRun(
        id="run-2",
        owner_user_id="owner1",
        job_id="job-1",
        trigger_id="t1",
        target_id="t1",
        status="queued",
        trigger_payload={},
        platform_job_id="loc_xyz",
        retry_count=1,
    )
    temp_repo.save_job_run(run)
    loaded = temp_repo.get_job_run_by_platform_job_id("loc_xyz", "owner1")
    assert loaded is not None
    assert loaded.platform_job_id == "loc_xyz"
    assert loaded.retry_count == 1


def test_list_job_runs_by_owner(temp_repo):
    """list_job_runs_by_owner returns runs for owner."""
    for i in range(3):
        run = JobRun(
            id=f"run-{i}",
            owner_user_id="owner1",
            job_id="job-1",
            trigger_id="t1",
            target_id="t1",
            status="succeeded",
            trigger_payload={},
        )
        temp_repo.save_job_run(run)
    runs = temp_repo.list_job_runs_by_owner("owner1")
    assert len(runs) == 3


def test_save_stage_run(temp_repo):
    """save_stage_run persists stage run."""
    job_run = JobRun(
        id="run-s1",
        owner_user_id="owner1",
        job_id="j1",
        trigger_id="t1",
        target_id="t1",
        status="running",
        trigger_payload={},
    )
    temp_repo.save_job_run(job_run)
    stage_run = StageRun(
        id="stage-run-1",
        job_run_id="run-s1",
        stage_id="stage-1",
        status="running",
        owner_user_id="owner1",
    )
    temp_repo.save_stage_run(stage_run)
    # No getter for stage run; verify no exception
    loaded_job = temp_repo.get_job_run("run-s1", "owner1")
    assert loaded_job is not None


def test_save_usage_record(temp_repo):
    """save_usage_record persists usage."""
    job_run = JobRun(
        id="run-u1",
        owner_user_id="owner1",
        job_id="j1",
        trigger_id="t1",
        target_id="t1",
        status="succeeded",
        trigger_payload={},
    )
    temp_repo.save_job_run(job_run)
    record = UsageRecord(
        id="usage-1",
        job_run_id="run-u1",
        usage_type="llm_tokens",
        provider="anthropic",
        metric_name="total_tokens",
        metric_value=100,
        owner_user_id="owner1",
    )
    temp_repo.save_usage_record(record)
    # No getter; verify no exception
    loaded = temp_repo.get_job_run("run-u1", "owner1")
    assert loaded is not None
