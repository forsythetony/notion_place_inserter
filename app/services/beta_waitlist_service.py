"""Business logic for beta waitlist intake."""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.repositories.supabase_beta_waitlist_repository import (
    SupabaseBetaWaitlistRepository,
)

_MAX_EMAIL_LENGTH = 320
_MAX_NAME = 200
_MAX_HEARD_OTHER = 500
_MAX_WORK_ROLE = 300
_MAX_NOTION_USE_CASE = 8000

HEARD_ABOUT_VALUES = frozenset(
    {
        "friend_or_colleague",
        "x_or_twitter",
        "linkedin",
        "search",
        "notion_community",
        "youtube_or_podcast",
        "other",
    }
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_email(email: str) -> tuple[str, str]:
    """Return (original_trimmed, normalized_lower) or raise ValueError."""
    raw = email.strip()
    if len(raw) > _MAX_EMAIL_LENGTH:
        raise ValueError("email is too long")
    lowered = raw.lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", lowered):
        raise ValueError("Invalid email address")
    return raw, lowered


def hash_client_ip(ip: str, salt: str) -> str:
    if not salt:
        salt = "waitlist-ip-hash-salt-unset"
    digest = hmac.new(
        salt.encode("utf-8"),
        ip.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:64]


class BetaWaitlistService:
    def __init__(
        self,
        repository: SupabaseBetaWaitlistRepository,
        *,
        ip_hash_salt: str,
    ) -> None:
        self._repo = repository
        self._ip_hash_salt = ip_hash_salt

    def _trim(self, s: str, max_len: int, field: str) -> str:
        t = s.strip()
        if len(t) > max_len:
            raise ValueError(f"{field} is too long")
        return t

    def persist_submission(
        self,
        *,
        email: str,
        name: str,
        heard_about: str,
        heard_about_other: str | None,
        work_role: str,
        notion_use_case: str,
        client_ip: str | None,
        user_agent: str | None,
        referrer: str | None,
        turnstile_verified: bool = False,
    ) -> None:
        raw_email, email_norm = normalize_email(email)
        name_t = self._trim(name, _MAX_NAME, "name")
        ha = heard_about.strip()
        if ha not in HEARD_ABOUT_VALUES:
            raise ValueError("heardAbout is invalid")
        other: str | None = None
        if ha == "other":
            if not heard_about_other or not heard_about_other.strip():
                raise ValueError("heardAboutOther is required when heardAbout is other")
            other = self._trim(heard_about_other, _MAX_HEARD_OTHER, "heardAboutOther")
        elif heard_about_other and heard_about_other.strip():
            raise ValueError("heardAboutOther must be empty unless heardAbout is other")
        wr = self._trim(work_role, _MAX_WORK_ROLE, "workRole")
        nu = self._trim(notion_use_case, _MAX_NOTION_USE_CASE, "notionUseCase")

        ip_hash = hash_client_ip(client_ip or "unknown", self._ip_hash_salt)
        ua = (user_agent or "")[:512]
        ref = (referrer or "")[:512]
        now = _utc_now_iso()

        captcha_fields: dict[str, Any]
        if turnstile_verified:
            captcha_fields = {
                "captcha_provider": "turnstile",
                "captcha_verified_at": now,
            }
        else:
            captcha_fields = {
                "captcha_provider": None,
                "captcha_verified_at": None,
            }

        existing = self._repo.get_by_email_normalized(email_norm)
        if existing:
            prev_count = int(existing.get("submission_count") or 1)
            update_row: dict[str, Any] = {
                "email": raw_email,
                "name": name_t,
                "heard_about": ha,
                "heard_about_other": other,
                "work_role": wr,
                "notion_use_case": nu,
                "submission_count": prev_count + 1,
                "last_submitted_at": now,
                "updated_at": now,
                "client_ip_hash": ip_hash,
                "user_agent": ua or None,
                "referrer": ref or None,
                **captcha_fields,
            }
            self._repo.update_resubmission(str(existing["id"]), update_row)
            logger.info("waitlist_resubmission | email_normalized_prefix={}", email_norm[:3])
            return

        insert_row: dict[str, Any] = {
            "email": raw_email,
            "email_normalized": email_norm,
            "name": name_t,
            "heard_about": ha,
            "heard_about_other": other,
            "work_role": wr,
            "notion_use_case": nu,
            "status": "PENDING_REVIEW",
            "submission_source": "landing_page_waitlist",
            "submission_count": 1,
            "first_submitted_at": now,
            "last_submitted_at": now,
            "client_ip_hash": ip_hash,
            "user_agent": ua or None,
            "referrer": ref or None,
            **captcha_fields,
        }
        self._repo.insert_submission(insert_row)
        logger.info("waitlist_new_submission | email_normalized_prefix={}", email_norm[:3])
