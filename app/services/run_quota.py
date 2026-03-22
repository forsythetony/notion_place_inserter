"""Helpers for production run quota RPC errors."""

from __future__ import annotations

from typing import Any


class RunQuotaExceeded(Exception):
    """Raised when ``enqueue_job_run_with_quota_check`` rejects due to UTC day/month caps."""

    def __init__(self, detail: dict[str, Any]) -> None:
        self.detail = detail
        super().__init__(detail.get("code", "run_quota_exceeded"))


def parse_run_quota_error_message(message: str) -> dict[str, Any] | None:
    """
    Parse ``RUN_QUOTA_EXCEEDED|period|limit|used`` from Postgres RAISE message.
    """
    if "RUN_QUOTA_EXCEEDED|" not in message:
        return None
    try:
        idx = message.index("RUN_QUOTA_EXCEEDED|")
        tail = message[idx + len("RUN_QUOTA_EXCEEDED|") :]
        parts = tail.split("|", 2)
        if len(parts) != 3:
            return None
        period, lim_s, used_s = parts
        return {
            "code": "run_quota_exceeded",
            "period": period,
            "limit": int(lim_s),
            "used": int(used_s),
        }
    except (ValueError, IndexError):
        return None
