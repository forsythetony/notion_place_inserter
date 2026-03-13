"""Shared FastAPI dependencies."""

import hmac
import os

from fastapi import Header, HTTPException
from loguru import logger


def require_auth(authorization: str | None = Header(default=None)):
    """Validate Authorization header matches SECRET."""
    secret = os.environ.get("SECRET", "")
    if not secret:
        logger.error("SECRET environment variable is not set")
        raise HTTPException(status_code=500, detail="Server misconfiguration")
    if not authorization or not hmac.compare_digest(authorization, secret):
        logger.warning("Unauthorized request: missing or invalid Authorization header")
        raise HTTPException(status_code=401, detail="Unauthorized")
