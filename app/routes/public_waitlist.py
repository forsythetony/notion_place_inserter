"""Public beta waitlist intake (unauthenticated)."""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.beta_waitlist_service import BetaWaitlistService
from app.services.turnstile_verification import verify_turnstile_token
from app.services.waitlist_rate_limiter import InMemoryWaitlistRateLimiter

router = APIRouter(prefix="/public", tags=["public"])


def _turnstile_enabled() -> bool:
    """Opt-in via TURNSTILE_ENABLED=1|true|yes. Default off: honeypot + rate limit + manual DB review only."""
    return os.environ.get("TURNSTILE_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


class PublicWaitlistRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=False)

    email: str = Field(..., min_length=3)
    name: str = Field(..., min_length=1)
    heard_about: str = Field(..., alias="heardAbout", min_length=1)
    heard_about_other: str | None = Field(default=None, alias="heardAboutOther")
    work_role: str = Field(..., alias="workRole", min_length=1)
    notion_use_case: str = Field(..., alias="notionUseCase", min_length=1)
    beta_fit_accepted: bool = Field(..., alias="betaFitAccepted")
    # Required when TURNSTILE_ENABLED; may be empty when Turnstile is off (see submit handler).
    captcha_token: str = Field(default="", alias="captchaToken")
    company_website: str = Field(default="", alias="companyWebsite")

    @field_validator("beta_fit_accepted")
    @classmethod
    def beta_fit_must_be_true(cls, v: bool) -> bool:
        if not v:
            raise ValueError("betaFitAccepted must be true")
        return v


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


@router.post("/waitlist", status_code=202)
async def submit_public_waitlist(request: Request, body: PublicWaitlistRequest):
    """
    Accept waitlist submission. Returns generic 202 for success, duplicate, or honeypot spam
    (anti-enumeration). Rate limits always; Turnstile only when TURNSTILE_ENABLED is set.
    """
    limiter: InMemoryWaitlistRateLimiter = request.app.state.waitlist_rate_limiter
    service: BetaWaitlistService = request.app.state.beta_waitlist_service

    ip = _client_ip(request)
    rl_key = f"waitlist:{ip or 'unknown'}"
    if not limiter.is_allowed(rl_key):
        raise HTTPException(status_code=429, detail="Too many requests; try again later.")

    honeypot = (body.company_website or "").strip()
    if honeypot:
        return {"status": "accepted"}

    # --- Cloudflare Turnstile (optional; enable later via TURNSTILE_ENABLED + keys) ---
    turnstile_on = _turnstile_enabled()
    if turnstile_on:
        secret = os.environ.get("TURNSTILE_SECRET_KEY", "").strip()
        if not secret:
            raise HTTPException(
                status_code=500,
                detail="Server misconfiguration: TURNSTILE_ENABLED but TURNSTILE_SECRET_KEY missing",
            )
        if not (body.captcha_token or "").strip():
            raise HTTPException(
                status_code=400, detail="Captcha token required when Turnstile is enabled"
            )
        if not verify_turnstile_token(secret, body.captcha_token, remote_ip=ip):
            raise HTTPException(status_code=400, detail="Captcha verification failed")

    try:
        service.persist_submission(
            email=body.email,
            name=body.name,
            heard_about=body.heard_about,
            heard_about_other=body.heard_about_other,
            work_role=body.work_role,
            notion_use_case=body.notion_use_case,
            client_ip=ip,
            user_agent=request.headers.get("user-agent"),
            referrer=request.headers.get("referer") or request.headers.get("referrer"),
            turnstile_verified=turnstile_on,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to save submission") from None

    return {"status": "accepted"}
