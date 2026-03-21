"""Runtime: skip external APIs when test config supplies manual_response."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.services.job_execution.runtime_types import ExecutionContext


def consume_manual_api_response(
    ctx: ExecutionContext,
    call_site_id: str,
) -> Any | None:
    """
    If ``api_overrides[call_site_id]`` has ``enabled: false`` and ``manual_response``, log and return it.

    If disabled without ``manual_response``, raise (should be blocked at analyze time).
    """
    raw = ctx.api_overrides.get(call_site_id)
    if not isinstance(raw, dict):
        return None
    if raw.get("enabled") is False:
        if "manual_response" in raw:
            logger.info(
                "external_api_skipped | run_id={} call_site={} reason=manual_fixture",
                ctx.run_id,
                call_site_id,
            )
            return raw.get("manual_response")
        raise ValueError(
            f"Call site {call_site_id!r} is disabled but manual_response is missing "
            "(run analyze / fix test configuration)."
        )
    return None
