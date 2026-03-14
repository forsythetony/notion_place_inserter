"""Shared FastAPI dependencies."""

import hmac
import os
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request
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


@dataclass(frozen=True)
class AuthContext:
    """Authenticated user context for managed-auth protected routes."""

    user_id: str
    email: str | None
    user_type: str


@dataclass(frozen=True)
class SignupAuthContext:
    """Authenticated user context for signup flows before profile creation."""

    user_id: str
    email: str | None


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Extract Bearer token from Authorization header. Returns None if missing or malformed."""
    if not authorization or not authorization.strip():
        return None
    parts = authorization.strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def require_managed_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthContext:
    """
    Validate Supabase Bearer token and resolve user profile for dashboard/auth routes.
    Raises 401 for missing/invalid/expired tokens; 403 when profile is missing.
    """
    token = _extract_bearer_token(authorization)
    if not token:
        logger.warning("managed_auth_rejected | reason=missing_or_malformed_bearer")
        raise HTTPException(status_code=401, detail="Unauthorized")

    supabase_client = getattr(request.app.state, "supabase_client", None)
    auth_repo = getattr(request.app.state, "supabase_auth_repository", None)
    if supabase_client is None or auth_repo is None:
        logger.error("managed_auth_rejected | reason=supabase_not_configured")
        raise HTTPException(status_code=500, detail="Server misconfiguration")

    try:
        user_response = supabase_client.auth.get_user(jwt=token)
    except Exception:
        logger.warning("managed_auth_rejected | reason=token_validation_failed")
        raise HTTPException(status_code=401, detail="Unauthorized")

    if user_response is None or getattr(user_response, "user", None) is None:
        logger.warning("managed_auth_rejected | reason=no_user_in_response")
        raise HTTPException(status_code=401, detail="Unauthorized")

    user = user_response.user
    user_id = str(getattr(user, "id", "") or "")
    if not user_id:
        logger.warning("managed_auth_rejected | reason=missing_user_id")
        raise HTTPException(status_code=401, detail="Unauthorized")

    profile = auth_repo.get_profile(user_id)
    if not profile:
        logger.warning(
            "managed_auth_rejected | reason=profile_not_found user_id={}", user_id
        )
        raise HTTPException(status_code=403, detail="Profile not found")

    user_type = profile.get("user_type")
    if not user_type:
        logger.warning(
            "managed_auth_rejected | reason=profile_missing_user_type user_id={}",
            user_id,
        )
        raise HTTPException(status_code=403, detail="Profile incomplete")

    email = getattr(user, "email", None)
    if email is not None:
        email = str(email)

    return AuthContext(user_id=user_id, email=email, user_type=user_type)


def require_admin_managed_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthContext:
    """
    Same as require_managed_auth but enforces user_type == ADMIN.
    Raises 403 with deterministic detail when caller is not an admin.
    """
    ctx = require_managed_auth(request=request, authorization=authorization)
    if ctx.user_type != "ADMIN":
        logger.warning(
            "admin_auth_rejected | reason=not_admin user_id={} user_type={}",
            ctx.user_id,
            ctx.user_type,
        )
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )
    return ctx


def require_signup_managed_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> SignupAuthContext:
    """
    Validate Supabase Bearer token for signup orchestration.
    Unlike require_managed_auth, this does not require an existing user profile.
    """
    token = _extract_bearer_token(authorization)
    if not token:
        logger.warning("signup_auth_rejected | reason=missing_or_malformed_bearer")
        raise HTTPException(status_code=401, detail="Unauthorized")

    supabase_client = getattr(request.app.state, "supabase_client", None)
    if supabase_client is None:
        logger.error("signup_auth_rejected | reason=supabase_not_configured")
        raise HTTPException(status_code=500, detail="Server misconfiguration")

    try:
        user_response = supabase_client.auth.get_user(jwt=token)
    except Exception:
        logger.warning("signup_auth_rejected | reason=token_validation_failed")
        raise HTTPException(status_code=401, detail="Unauthorized")

    if user_response is None or getattr(user_response, "user", None) is None:
        logger.warning("signup_auth_rejected | reason=no_user_in_response")
        raise HTTPException(status_code=401, detail="Unauthorized")

    user = user_response.user
    user_id = str(getattr(user, "id", "") or "")
    if not user_id:
        logger.warning("signup_auth_rejected | reason=missing_user_id")
        raise HTTPException(status_code=401, detail="Unauthorized")

    email = getattr(user, "email", None)
    if email is not None:
        email = str(email)

    return SignupAuthContext(user_id=user_id, email=email)
