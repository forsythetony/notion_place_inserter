"""Cloudflare Turnstile server-side verification."""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile_token(
    secret: str,
    token: str,
    *,
    remote_ip: str | None = None,
    timeout_seconds: float = 10.0,
) -> bool:
    """
    Returns True if Turnstile accepts the token.
    On network/parse errors, logs and returns False.
    """
    if not secret or not token or not token.strip():
        return False
    data: dict[str, Any] = {
        "secret": secret,
        "response": token.strip(),
    }
    if remote_ip:
        data["remoteip"] = remote_ip
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            r = client.post(TURNSTILE_VERIFY_URL, data=data)
            r.raise_for_status()
            body = r.json()
    except Exception as e:
        logger.warning("turnstile_verify_request_failed | error={}", e)
        return False
    success = bool(body.get("success"))
    if not success:
        codes = body.get("error-codes") or body.get("error_codes")
        logger.info("turnstile_verify_rejected | codes={}", codes)
    return success
