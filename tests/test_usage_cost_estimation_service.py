"""Tests for usage cost estimation (rate cards)."""

from app.domain.runs import UsageRecord
from app.services.usage_cost_estimation_service import (
    RateCardRow,
    estimate_usage_record_usd,
    sum_estimated_usd,
)


def _row(**kw) -> RateCardRow:
    base = {
        "provider": "x",
        "usage_type": "external_api_call",
        "rate_key": "*",
        "usd_per_million_input_tokens": None,
        "usd_per_million_output_tokens": None,
        "usd_per_million_total_tokens": None,
        "usd_per_call": None,
    }
    base.update(kw)
    return RateCardRow(**base)


def test_external_api_call_uses_operation_match():
    rows = [
        _row(
            provider="freepik",
            usage_type="external_api_call",
            rate_key="search_icons",
            usd_per_call=0.001,
        )
    ]
    ur = UsageRecord(
        id="u1",
        job_run_id="j1",
        usage_type="external_api_call",
        provider="freepik",
        metric_name="search_icons",
        metric_value=1,
    )
    assert estimate_usage_record_usd(ur, rows) == 0.001


def test_llm_tokens_uses_prompt_completion_when_present():
    rows = [
        _row(
            provider="anthropic",
            usage_type="llm_tokens",
            rate_key="*",
            usd_per_million_input_tokens=3.0,
            usd_per_million_output_tokens=15.0,
            usd_per_million_total_tokens=None,
            usd_per_call=None,
        )
    ]
    ur = UsageRecord(
        id="u1",
        job_run_id="j1",
        usage_type="llm_tokens",
        provider="anthropic",
        metric_name="total_tokens",
        metric_value=1000,
        metadata={"prompt_tokens": 400, "completion_tokens": 600, "model": "m"},
    )
    # (400/1e6)*3 + (600/1e6)*15 = 0.0012 + 0.009 = 0.0102
    assert abs(estimate_usage_record_usd(ur, rows) - 0.0102) < 1e-9


def test_sum_estimated_usd():
    rows = [
        _row(
            provider="anthropic",
            usage_type="llm_tokens",
            rate_key="*",
            usd_per_million_input_tokens=None,
            usd_per_million_output_tokens=None,
            usd_per_million_total_tokens=9.0,
            usd_per_call=None,
        )
    ]
    ur = UsageRecord(
        id="u1",
        job_run_id="j1",
        usage_type="llm_tokens",
        provider="anthropic",
        metric_name="total_tokens",
        metric_value=1_000_000,
        metadata={"model": "m"},
    )
    assert sum_estimated_usd([ur], rows) == 9.0
