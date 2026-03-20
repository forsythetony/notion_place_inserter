"""Tests for one-trigger-per-job API policy (enforced in attach, not DB)."""

import pytest

from app.domain.errors import (
    TriggerJobLinkPolicyError,
    validate_one_trigger_per_job_attach,
)


def test_validate_attach_empty_allowed():
    validate_one_trigger_per_job_attach([], "trigger_a")


def test_validate_attach_same_trigger_idempotent():
    validate_one_trigger_per_job_attach(["trigger_a"], "trigger_a")


def test_validate_attach_rejects_different_trigger():
    with pytest.raises(TriggerJobLinkPolicyError) as exc:
        validate_one_trigger_per_job_attach(["trigger_a"], "trigger_b")
    assert exc.value.code == "JOB_ALREADY_HAS_TRIGGER"


def test_validate_attach_rejects_multiple_existing():
    with pytest.raises(TriggerJobLinkPolicyError) as exc:
        validate_one_trigger_per_job_attach(["t2", "t1"], "t1")
    assert exc.value.code == "JOB_MULTIPLE_TRIGGERS"
