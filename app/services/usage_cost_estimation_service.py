"""Estimate USD cost for usage_records using usage_rate_cards (admin analytics only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.domain.runs import UsageRecord


@dataclass(frozen=True)
class RateCardRow:
    provider: str
    usage_type: str
    rate_key: str
    usd_per_million_input_tokens: float | None
    usd_per_million_output_tokens: float | None
    usd_per_million_total_tokens: float | None
    usd_per_call: float | None


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_rate_card_rows(raw: list[dict[str, Any]]) -> list[RateCardRow]:
    out: list[RateCardRow] = []
    for row in raw:
        try:
            out.append(
                RateCardRow(
                    provider=str(row["provider"]),
                    usage_type=str(row["usage_type"]),
                    rate_key=str(row.get("rate_key") or "*"),
                    usd_per_million_input_tokens=_f(row.get("usd_per_million_input_tokens")),
                    usd_per_million_output_tokens=_f(row.get("usd_per_million_output_tokens")),
                    usd_per_million_total_tokens=_f(row.get("usd_per_million_total_tokens")),
                    usd_per_call=_f(row.get("usd_per_call")),
                )
            )
        except (KeyError, TypeError) as e:
            logger.warning("usage_rate_card_skip_row | error={}", e)
    return out


def _pick_llm_row(rows: list[RateCardRow], provider: str, model: str | None) -> RateCardRow | None:
    cands = [r for r in rows if r.provider == provider and r.usage_type == "llm_tokens"]
    if not cands:
        return None
    m = (model or "").strip()
    if m:
        for r in cands:
            if r.rate_key == m:
                return r
    for r in cands:
        if r.rate_key == "*":
            return r
    return cands[0]


def _pick_external_row(rows: list[RateCardRow], provider: str, operation: str) -> RateCardRow | None:
    cands = [r for r in rows if r.provider == provider and r.usage_type == "external_api_call"]
    if not cands:
        return None
    op = (operation or "").strip()
    if op:
        for r in cands:
            if r.rate_key == op:
                return r
    for r in cands:
        if r.rate_key == "*":
            return r
    return cands[0]


def estimate_usage_record_usd(record: UsageRecord, rows: list[RateCardRow]) -> float:
    """Return a single record's estimated USD (0 if no matching rate)."""
    if record.usage_type == "llm_tokens":
        rc = _pick_llm_row(rows, record.provider, (record.metadata or {}).get("model") if record.metadata else None)
        if rc is None:
            return 0.0
        meta = record.metadata or {}
        pt = meta.get("prompt_tokens")
        ct = meta.get("completion_tokens")
        try:
            pi = int(pt) if pt is not None else None
            co = int(ct) if ct is not None else None
        except (TypeError, ValueError):
            pi = co = None
        total = float(record.metric_value)
        if pi is not None and co is not None and rc.usd_per_million_input_tokens is not None and rc.usd_per_million_output_tokens is not None:
            return (pi / 1_000_000.0) * rc.usd_per_million_input_tokens + (co / 1_000_000.0) * rc.usd_per_million_output_tokens
        if rc.usd_per_million_total_tokens is not None:
            return (total / 1_000_000.0) * rc.usd_per_million_total_tokens
        if rc.usd_per_million_input_tokens is not None and rc.usd_per_million_output_tokens is not None:
            half = total / 2.0
            return (half / 1_000_000.0) * (rc.usd_per_million_input_tokens + rc.usd_per_million_output_tokens)
        return 0.0

    if record.usage_type == "external_api_call":
        rc = _pick_external_row(rows, record.provider, record.metric_name)
        if rc is None or rc.usd_per_call is None:
            return 0.0
        n = float(record.metric_value)
        return n * rc.usd_per_call

    return 0.0


def sum_estimated_usd(records: list[UsageRecord], rows: list[RateCardRow]) -> float:
    return sum(estimate_usage_record_usd(ur, rows) for ur in records)
