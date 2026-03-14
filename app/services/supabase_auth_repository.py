"""User profile and invitation code persistence via Supabase tables."""

import secrets
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

INVITATION_CODE_LENGTH = 20
MAX_ISSUE_RETRIES = 3


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

    def get_invitation_by_issued_to(self, issued_to: str) -> dict[str, Any] | None:
        """
        Fetch invitation by exact issued_to. Returns first match by created_at ascending.
        Use for idempotent issuance: non-empty issued_to must be unique.
        """
        if not issued_to or not issued_to.strip():
            return None
        try:
            resp = (
                self._client.table(self._config.table_invitation_codes)
                .select("*")
                .eq("issued_to", issued_to.strip())
                .order("created_at")
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception(
                "supabase_get_invitation_by_issued_to_failed | issued_to={}",
                issued_to[:20] + "..." if len(issued_to) > 20 else issued_to,
            )
            raise

        data = resp.data
        if not data or (isinstance(data, list) and len(data) == 0):
            return None
        row = data[0] if isinstance(data, list) else data
        return dict(row) if isinstance(row, dict) else None

    def generate_invitation_code(self) -> str:
        """Generate a unique 20-character invitation code. Retries on collision."""
        for _ in range(MAX_ISSUE_RETRIES):
            code = secrets.token_hex(INVITATION_CODE_LENGTH // 2)
            if len(code) != INVITATION_CODE_LENGTH:
                code = (code + secrets.token_hex(1))[:INVITATION_CODE_LENGTH]
            existing = self.get_invitation_code_by_code(code)
            if existing is None:
                return code
            logger.warning(
                "invitation_code_collision | code_preview={}",
                code[:8] + "...",
            )
        raise RuntimeError(
            f"Failed to generate unique invitation code after {MAX_ISSUE_RETRIES} attempts"
        )

    def validate_invitation_code(self, code: str) -> dict[str, Any]:
        """
        Validate invitation code. Returns deterministic status dict:
        - {"status": "valid", "user_type": str, "id": str} when claimable
        - {"status": "already_claimed"} when code exists but claimed
        - {"status": "invalid"} when code not found
        """
        row = self.get_invitation_code_by_code(code)
        if row is None:
            return {"status": "invalid"}
        if row.get("claimed") is True:
            return {"status": "already_claimed"}
        return {
            "status": "valid",
            "user_type": row["user_type"],
            "id": str(row["id"]),
        }

    def claim_invitation_code(
        self,
        code: str,
        claimed_by_user_id: UUID | str,
    ) -> dict[str, Any] | None:
        """
        Atomically claim an unclaimed invitation code. Returns claimed row if
        successful, None if code not found or already claimed (race-safe).
        """
        uid = (
            str(claimed_by_user_id)
            if isinstance(claimed_by_user_id, UUID)
            else claimed_by_user_id
        )
        now = datetime.now(timezone.utc).isoformat()
        payload: dict[str, Any] = {
            "claimed": True,
            "date_claimed": now,
            "claimed_at": now,
            "claimed_by_user_id": uid,
        }
        try:
            resp = (
                self._client.table(self._config.table_invitation_codes)
                .update(payload)
                .eq("code", code)
                .eq("claimed", False)
                .execute()
            )
        except Exception:
            logger.exception(
                "supabase_claim_invitation_code_failed | code={}",
                code[:8] + "..." if len(code) > 8 else code,
            )
            raise

        data = resp.data
        if not data or (isinstance(data, list) and len(data) == 0):
            return None
        row = data[0] if isinstance(data, list) else data
        return dict(row) if isinstance(row, dict) else None

    def claim_invitation_code_for_signup(
        self,
        code: str,
        user_id: UUID | str,
    ) -> dict[str, Any] | None:
        """
        Atomically claim an invitation code and provision/update user profile.
        Returns claimed row on success, None if code invalid or already claimed.
        """
        row = self.claim_invitation_code(code, user_id)
        if row is None:
            return None
        self.upsert_profile(
            user_id,
            row["user_type"],
            invitation_code_id=row["id"],
        )
        return row
