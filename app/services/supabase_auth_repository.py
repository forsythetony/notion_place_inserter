"""User profile and invitation code persistence via Supabase tables."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from loguru import logger
from supabase import Client

from app.integrations.supabase_config import SupabaseConfig

USER_TYPE_ADMIN = "ADMIN"
USER_TYPE_STANDARD = "STANDARD"
USER_TYPE_BETA_TESTER = "BETA_TESTER"
USER_TYPES = (USER_TYPE_ADMIN, USER_TYPE_STANDARD, USER_TYPE_BETA_TESTER)


class SupabaseAuthRepository:
    """
    Repository for user_profiles and invitation_codes.
    Thin persistence layer; easy to fake in unit tests.
    """

    def __init__(self, client: Client, config: SupabaseConfig) -> None:
        self._client = client
        self._config = config

    def upsert_profile(
        self,
        user_id: UUID | str,
        user_type: str,
        *,
        invitation_code_id: UUID | str | None = None,
    ) -> None:
        """Insert or update a user profile. Enforces user_type enum values."""
        if user_type not in USER_TYPES:
            raise ValueError(
                f"user_type must be one of {USER_TYPES}, got {user_type!r}"
            )
        uid = str(user_id) if isinstance(user_id, UUID) else user_id
        payload: dict[str, Any] = {
            "user_id": uid,
            "user_type": user_type,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if invitation_code_id is not None:
            payload["invitation_code_id"] = (
                str(invitation_code_id)
                if isinstance(invitation_code_id, UUID)
                else invitation_code_id
            )

        try:
            self._client.table(self._config.table_user_profiles).upsert(
                payload,
                on_conflict="user_id",
            ).execute()
        except Exception:
            logger.exception(
                "supabase_upsert_profile_failed | user_id={} user_type={}",
                uid,
                user_type,
            )
            raise

    def get_profile(self, user_id: UUID | str) -> dict[str, Any] | None:
        """Fetch user profile by user_id. Returns None if not found."""
        uid = str(user_id) if isinstance(user_id, UUID) else user_id
        try:
            resp = (
                self._client.table(self._config.table_user_profiles)
                .select("*")
                .eq("user_id", uid)
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception("supabase_get_profile_failed | user_id={}", uid)
            raise

        data = resp.data
        if not data or (isinstance(data, list) and len(data) == 0):
            return None
        row = data[0] if isinstance(data, list) else data
        return dict(row) if isinstance(row, dict) else None

    def create_invitation_code(
        self,
        code: str,
        user_type: str,
        *,
        issued_to: str | None = None,
        platform_issued_on: str | None = None,
    ) -> dict[str, Any]:
        """Insert an unclaimed invitation code. Returns created row."""
        if user_type not in USER_TYPES:
            raise ValueError(
                f"user_type must be one of {USER_TYPES}, got {user_type!r}"
            )
        if len(code) != 20:
            raise ValueError(f"code must be exactly 20 characters, got {len(code)}")

        payload: dict[str, Any] = {
            "code": code,
            "user_type": user_type,
            "claimed": False,
        }
        if issued_to is not None:
            payload["issued_to"] = issued_to
        if platform_issued_on is not None:
            payload["platform_issued_on"] = platform_issued_on

        try:
            resp = (
                self._client.table(self._config.table_invitation_codes)
                .insert(payload)
                .execute()
            )
        except Exception:
            logger.exception(
                "supabase_create_invitation_code_failed | code={} user_type={}",
                code[:8] + "...",
                user_type,
            )
            raise

        data = resp.data
        if not data or (isinstance(data, list) and len(data) == 0):
            raise RuntimeError("insert returned no data")
        row = data[0] if isinstance(data, list) else data
        return dict(row) if isinstance(row, dict) else {}

    def get_invitation_code_by_code(
        self, code: str
    ) -> dict[str, Any] | None:
        """Fetch invitation code by code. Returns None if not found."""
        try:
            resp = (
                self._client.table(self._config.table_invitation_codes)
                .select("*")
                .eq("code", code)
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception(
                "supabase_get_invitation_code_failed | code={}",
                code[:8] + "..." if len(code) > 8 else code,
            )
            raise

        data = resp.data
        if not data or (isinstance(data, list) and len(data) == 0):
            return None
        row = data[0] if isinstance(data, list) else data
        return dict(row) if isinstance(row, dict) else None
