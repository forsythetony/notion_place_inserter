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

_COHORT_UNSET = object()


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
        cohort_id: Any = _COHORT_UNSET,
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
        if cohort_id is not _COHORT_UNSET:
            if cohort_id is None:
                payload["cohort_id"] = None
            else:
                payload["cohort_id"] = (
                    str(cohort_id) if isinstance(cohort_id, UUID) else cohort_id
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
        cohort_id: UUID | str | None = None,
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
        if cohort_id is not None:
            payload["cohort_id"] = (
                str(cohort_id) if isinstance(cohort_id, UUID) else cohort_id
            )

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
            cohort_id=row.get("cohort_id"),
        )
        return row

    def get_invitation_by_id(
        self, invitation_id: UUID | str
    ) -> dict[str, Any] | None:
        """Fetch invitation by primary key."""
        iid = str(invitation_id) if isinstance(invitation_id, UUID) else invitation_id
        try:
            resp = (
                self._client.table(self._config.table_invitation_codes)
                .select("*")
                .eq("id", iid)
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception("supabase_get_invitation_by_id_failed | id={}", iid)
            raise
        data = resp.data
        if not data or (isinstance(data, list) and len(data) == 0):
            return None
        row = data[0] if isinstance(data, list) else data
        return dict(row) if isinstance(row, dict) else None

    def list_invitation_codes_for_admin(self) -> list[dict[str, Any]]:
        """All invitation rows, newest first, with cohort_key merged."""
        try:
            resp = (
                self._client.table(self._config.table_invitation_codes)
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
        except Exception:
            logger.exception("supabase_list_invitation_codes_failed")
            raise
        rows = list(resp.data or [])
        cohort_ids = {r.get("cohort_id") for r in rows if r.get("cohort_id")}
        key_by_id = self._cohort_keys_by_id(
            [str(x) for x in cohort_ids if x is not None]
        )
        email_map = self._auth_user_id_to_email_map()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            cid = d.get("cohort_id")
            d["cohort_key"] = key_by_id.get(str(cid)) if cid else None
            claimer = d.get("claimed_by_user_id")
            if claimer:
                d["claimed_by_email"] = email_map.get(str(claimer))
            else:
                d["claimed_by_email"] = None
            out.append(d)
        return out

    def delete_unclaimed_invitation_by_id(
        self, invitation_id: UUID | str
    ) -> str:
        """
        Delete invitation by id when unclaimed.
        Returns 'not_found' | 'claimed' | 'deleted'.
        """
        row = self.get_invitation_by_id(invitation_id)
        if row is None:
            return "not_found"
        if row.get("claimed") is True:
            return "claimed"
        iid = str(invitation_id) if isinstance(invitation_id, UUID) else invitation_id
        try:
            self._client.table(self._config.table_invitation_codes).delete().eq(
                "id", iid
            ).eq("claimed", False).execute()
        except Exception:
            logger.exception("supabase_delete_invitation_failed | id={}", iid)
            raise
        return "deleted"

    def list_user_profiles_for_admin(self) -> list[dict[str, Any]]:
        """All user_profiles rows, newest first, with cohort_key merged."""
        try:
            resp = (
                self._client.table(self._config.table_user_profiles)
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
        except Exception:
            logger.exception("supabase_list_user_profiles_admin_failed")
            raise
        rows = list(resp.data or [])
        cohort_ids = {r.get("cohort_id") for r in rows if r.get("cohort_id")}
        key_by_id = self._cohort_keys_by_id(
            [str(x) for x in cohort_ids if x is not None]
        )
        email_map = self._auth_user_id_to_email_map()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            cid = d.get("cohort_id")
            d["cohort_key"] = key_by_id.get(str(cid)) if cid else None
            uid = str(d.get("user_id") or "")
            d["email"] = email_map.get(uid) if uid else None
            out.append(d)
        return out

    def _auth_user_id_to_email_map(self) -> dict[str, str]:
        """
        Map Supabase Auth user id -> email via Admin API (paginated).
        Returns empty dict on failure so callers can still return DB rows.

        supabase-py returns a list[User] from list_users(); older mocks may return
        an object with a .users attribute — normalize both.
        """
        out: dict[str, str] = {}
        page = 1
        per_page = 1000
        try:
            while True:
                raw = self._client.auth.admin.list_users(
                    page=page, per_page=per_page
                )
                if isinstance(raw, list):
                    users = raw
                else:
                    users = list(getattr(raw, "users", None) or [])
                for u in users:
                    uid = str(getattr(u, "id", "") or "")
                    em = getattr(u, "email", None)
                    if uid and em:
                        out[uid] = str(em)
                if len(users) < per_page:
                    break
                page += 1
        except Exception as e:
            logger.warning(
                "supabase_auth_list_users_for_email_map_failed | error={}",
                e,
            )
            return {}
        return out

    def _cohort_keys_by_id(self, cohort_ids: list[str]) -> dict[str, str]:
        if not cohort_ids:
            return {}
        try:
            resp = (
                self._client.table(self._config.table_user_cohorts)
                .select("id, key")
                .in_("id", cohort_ids)
                .execute()
            )
        except Exception:
            logger.exception("supabase_cohort_keys_lookup_failed")
            raise
        out: dict[str, str] = {}
        for c in resp.data or []:
            if isinstance(c, dict) and c.get("id") is not None:
                out[str(c["id"])] = str(c["key"])
        return out

    def get_cohort_by_id(self, cohort_id: UUID | str) -> dict[str, Any] | None:
        cid = str(cohort_id) if isinstance(cohort_id, UUID) else cohort_id
        try:
            resp = (
                self._client.table(self._config.table_user_cohorts)
                .select("*")
                .eq("id", cid)
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception("supabase_get_cohort_by_id_failed | id={}", cid)
            raise
        data = resp.data
        if not data or (isinstance(data, list) and len(data) == 0):
            return None
        row = data[0] if isinstance(data, list) else data
        return dict(row) if isinstance(row, dict) else None

    def get_cohort_by_key(self, key: str) -> dict[str, Any] | None:
        if not key or not key.strip():
            return None
        try:
            resp = (
                self._client.table(self._config.table_user_cohorts)
                .select("*")
                .eq("key", key.strip())
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception("supabase_get_cohort_by_key_failed")
            raise
        data = resp.data
        if not data or (isinstance(data, list) and len(data) == 0):
            return None
        row = data[0] if isinstance(data, list) else data
        return dict(row) if isinstance(row, dict) else None

    def list_cohorts(self) -> list[dict[str, Any]]:
        try:
            resp = (
                self._client.table(self._config.table_user_cohorts)
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
        except Exception:
            logger.exception("supabase_list_cohorts_failed")
            raise
        return [dict(r) for r in (resp.data or []) if isinstance(r, dict)]

    def create_cohort(self, key: str, description: str | None) -> dict[str, Any]:
        k = key.strip()
        if not k:
            raise ValueError("cohort key must be non-empty")
        payload: dict[str, Any] = {"key": k}
        if description is not None:
            payload["description"] = description
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            resp = (
                self._client.table(self._config.table_user_cohorts)
                .insert(payload)
                .execute()
            )
        except Exception:
            logger.exception("supabase_create_cohort_failed | key={}", k[:40])
            raise
        data = resp.data
        if not data or (isinstance(data, list) and len(data) == 0):
            raise RuntimeError("insert cohort returned no data")
        row = data[0] if isinstance(data, list) else data
        return dict(row) if isinstance(row, dict) else {}

    def update_cohort_description(
        self, cohort_id: UUID | str, description: str | None
    ) -> dict[str, Any] | None:
        cid = str(cohort_id) if isinstance(cohort_id, UUID) else cohort_id
        payload: dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "description": description,
        }
        try:
            resp = (
                self._client.table(self._config.table_user_cohorts)
                .update(payload)
                .eq("id", cid)
                .execute()
            )
        except Exception:
            logger.exception("supabase_update_cohort_failed | id={}", cid)
            raise
        data = resp.data
        if not data or (isinstance(data, list) and len(data) == 0):
            return None
        row = data[0] if isinstance(data, list) else data
        return dict(row) if isinstance(row, dict) else None

    def cohort_has_references(self, cohort_id: str) -> bool:
        try:
            inv = (
                self._client.table(self._config.table_invitation_codes)
                .select("id")
                .eq("cohort_id", cohort_id)
                .limit(1)
                .execute()
            )
            if inv.data:
                return True
            prof = (
                self._client.table(self._config.table_user_profiles)
                .select("user_id")
                .eq("cohort_id", cohort_id)
                .limit(1)
                .execute()
            )
            return bool(prof.data)
        except Exception:
            logger.exception("supabase_cohort_references_check_failed | id={}", cohort_id)
            raise

    def delete_cohort_if_unused(self, cohort_id: UUID | str) -> str:
        """Returns 'not_found' | 'in_use' | 'deleted'."""
        cid = str(cohort_id) if isinstance(cohort_id, UUID) else cohort_id
        row = self.get_cohort_by_id(cid)
        if row is None:
            return "not_found"
        if self.cohort_has_references(cid):
            return "in_use"
        try:
            self._client.table(self._config.table_user_cohorts).delete().eq(
                "id", cid
            ).execute()
        except Exception:
            logger.exception("supabase_delete_cohort_failed | id={}", cid)
            raise
        return "deleted"
