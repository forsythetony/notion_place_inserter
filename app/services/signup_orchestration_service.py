"""Signup orchestration: validate invite before creating auth user, with compensation on failure."""

from typing import Any

from loguru import logger
from supabase import Client

from app.services.supabase_auth_repository import SupabaseAuthRepository


class SignupOrchestrationService:
    """
    Orchestrates invite-required signup: validates code first, creates auth user
    only when valid, claims invite and provisions profile. Deletes orphan auth user
    if claim/profile provisioning fails.
    """

    def __init__(self, supabase_client: Client, auth_repo: SupabaseAuthRepository) -> None:
        self._client = supabase_client
        self._auth_repo = auth_repo

    def signup_with_invitation(
        self,
        email: str,
        password: str,
        code: str,
    ) -> dict[str, Any]:
        """
        Validate invite, create auth user, claim code, provision profile.
        Returns {"user_id": str} on success.
        Raises ValueError with deterministic message for invalid/already-claimed code.
        """
        if not code or len(code) != 20:
            raise ValueError("Invalid invitation code")
        if not email or not email.strip():
            raise ValueError("Email is required")
        if not password or len(password) < 6:
            raise ValueError("Password must be at least 6 characters")

        # Step 1: validate invite before any user creation
        validation = self._auth_repo.validate_invitation_code(code)
        if validation["status"] == "invalid":
            raise ValueError("Invalid invitation code")
        if validation["status"] == "already_claimed":
            raise ValueError("Invitation code already claimed")

        user_type = validation["user_type"]

        # Step 2: create auth user via admin API
        try:
            create_resp = self._client.auth.admin.create_user(
                {
                    "email": email.strip(),
                    "password": password,
                    "email_confirm": True,
                }
            )
        except Exception as e:
            logger.exception("signup_create_user_failed | email={}", email[:20] + "...")
            msg = str(e).lower()
            if "already registered" in msg or "already exists" in msg or "duplicate" in msg:
                raise ValueError("An account with this email already exists") from e
            raise ValueError("Sign-up failed. Please try again.") from e

        user = getattr(create_resp, "user", None) if create_resp else None
        if not user:
            raise ValueError("Sign-up failed. Please try again.")

        user_id = str(getattr(user, "id", "") or "")
        if not user_id:
            raise ValueError("Sign-up failed. Please try again.")

        # Step 3: claim invite and provision profile; compensate on failure
        try:
            row = self._auth_repo.claim_invitation_code_for_signup(code, user_id)
            if row is None:
                # Race: code was claimed between validation and now
                self._delete_auth_user(user_id)
                raise ValueError("Invitation code already claimed")
            return {"user_id": user_id, "user_type": user_type}
        except ValueError:
            raise
        except Exception as e:
            logger.exception(
                "signup_claim_or_profile_failed | user_id={} code_preview={}",
                user_id,
                code[:8] + "...",
            )
            self._delete_auth_user(user_id)
            raise ValueError("Sign-up failed. Please try again.") from e

    def _delete_auth_user(self, user_id: str) -> None:
        """Delete auth user (compensation for failed claim/profile provisioning)."""
        try:
            self._client.auth.admin.delete_user(user_id)
            logger.info("signup_compensation_deleted_orphan | user_id={}", user_id)
        except Exception:
            logger.exception(
                "signup_compensation_delete_failed | user_id={}",
                user_id,
            )
