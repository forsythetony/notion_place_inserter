"""Invitation code issuance and claim routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import (
    AuthContext,
    SignupAuthContext,
    require_admin_managed_auth,
    require_managed_auth,
    require_signup_managed_auth,
)
from app.services.supabase_auth_repository import USER_TYPES

router = APIRouter(prefix="/auth/invitations", tags=["auth", "invitations"])


def _iso_or_raw(value: object) -> object:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _invitation_row_to_list_item(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "code": row["code"],
        "userType": row["user_type"],
        "cohortId": str(row["cohort_id"]) if row.get("cohort_id") else None,
        "cohortKey": row.get("cohort_key"),
        "issuedTo": row.get("issued_to"),
        "platformIssuedOn": row.get("platform_issued_on"),
        "claimed": bool(row.get("claimed")),
        "dateIssued": _iso_or_raw(row.get("date_issued")),
        "dateClaimed": _iso_or_raw(row.get("date_claimed")),
        "claimedAt": _iso_or_raw(row.get("claimed_at")),
        "claimedByUserId": str(row["claimed_by_user_id"])
        if row.get("claimed_by_user_id")
        else None,
        "claimedByEmail": row.get("claimed_by_email"),
        "createdAt": _iso_or_raw(row.get("created_at")),
    }


def _issue_response_body(row: dict) -> dict:
    """POST /auth/invitations JSON (snake_case legacy + cohortId for admin UI)."""
    out = {
        "code": row["code"],
        "id": str(row["id"]),
        "user_type": row["user_type"],
        "issued_to": row.get("issued_to"),
        "platform_issued_on": row.get("platform_issued_on"),
        "claimed": bool(row.get("claimed", False)),
    }
    cid = row.get("cohort_id")
    out["cohortId"] = str(cid) if cid else None
    out["cohort_id"] = out["cohortId"]
    return out


class InvitationIssueRequest(BaseModel):
    """Request body for POST /auth/invitations (admin-only)."""

    model_config = ConfigDict(populate_by_name=True)

    user_type: str = Field(alias="userType")
    issued_to: str | None = Field(default=None, alias="issuedTo")
    platform_issued_on: str | None = Field(default=None, alias="platformIssuedOn")
    cohort_id: UUID | None = Field(default=None, alias="cohortId")


class InvitationValidateRequest(BaseModel):
    """Request body for POST /auth/invitations/validate."""

    code: str


class InvitationClaimRequest(BaseModel):
    """Request body for POST /auth/invitations/claim."""

    code: str


@router.get("")
def list_invitations(
    request: Request,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    """List all invitation codes (admin-only). Client filters in v1."""
    auth_repo = request.app.state.supabase_auth_repository
    logger.info("admin_list_invitations | admin_user_id={}", ctx.user_id)
    rows = auth_repo.list_invitation_codes_for_admin()
    return {"items": [_invitation_row_to_list_item(r) for r in rows]}


@router.delete("/{invitation_id}", status_code=204)
def delete_invitation(
    request: Request,
    invitation_id: UUID,
    ctx: AuthContext = Depends(require_admin_managed_auth),
):
    """Revoke an unclaimed invitation (admin-only)."""
    auth_repo = request.app.state.supabase_auth_repository
    result = auth_repo.delete_unclaimed_invitation_by_id(invitation_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Invitation not found")
    if result == "claimed":
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a claimed invitation",
        )
    logger.info(
        "admin_delete_invitation | admin_user_id={} invitation_id={}",
        ctx.user_id,
        invitation_id,
    )


@router.post("")
def issue_invitation(
    request: Request,
    body: InvitationIssueRequest,
    _ctx: AuthContext = Depends(require_admin_managed_auth),
):
    """
    Create a new invitation code. Admin-only.
    Accepts userType, issuedTo, platformIssuedOn in POST body.
    """
    if body.user_type not in USER_TYPES:
        logger.warning(
            "invite_issue_rejected | reason=invalid_user_type user_type={}",
            body.user_type,
        )
        raise HTTPException(
            status_code=400,
            detail=f"userType must be one of {USER_TYPES}, got {body.user_type!r}",
        )
    auth_repo = request.app.state.supabase_auth_repository

    cohort_id_str: str | None = None
    if body.cohort_id is not None:
        cohort = auth_repo.get_cohort_by_id(body.cohort_id)
        if cohort is None:
            raise HTTPException(
                status_code=400,
                detail="cohortId does not reference an existing cohort",
            )
        cohort_id_str = str(body.cohort_id)

    # Idempotent: if issuedTo is non-empty and already exists, return existing row
    if body.issued_to and body.issued_to.strip():
        existing = auth_repo.get_invitation_by_issued_to(body.issued_to)
        if existing is not None:
            return _issue_response_body(existing)

    code = auth_repo.generate_invitation_code()
    row = auth_repo.create_invitation_code(
        code=code,
        user_type=body.user_type,
        issued_to=body.issued_to,
        platform_issued_on=body.platform_issued_on,
        cohort_id=cohort_id_str,
    )
    return _issue_response_body(row)


@router.post("/validate")
def validate_invitation(
    request: Request,
    body: InvitationValidateRequest,
    _ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Validate an invitation code. Returns deterministic status:
    valid (claimable), invalid (not found), or already_claimed.
    """
    if not body.code or len(body.code) != 20:
        logger.debug(
            "invite_validate_rejected | reason=invalid_code_format code_len={}",
            len(body.code) if body.code else 0,
        )
        return {"status": "invalid"}
    auth_repo = request.app.state.supabase_auth_repository
    result = auth_repo.validate_invitation_code(body.code)
    return result


@router.post("/claim")
def claim_invitation(
    request: Request,
    body: InvitationClaimRequest,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Atomically claim an invitation code. Single-use; second attempt fails.
    Returns user_type for signup provisioning when successful.
    """
    if not body.code or len(body.code) != 20:
        logger.warning(
            "invite_claim_rejected | reason=invalid_code_format user_id={}",
            ctx.user_id,
        )
        raise HTTPException(status_code=400, detail="Invalid invitation code")
    auth_repo = request.app.state.supabase_auth_repository
    validation = auth_repo.validate_invitation_code(body.code)
    if validation["status"] == "invalid":
        logger.warning(
            "invite_claim_rejected | reason=invalid_code user_id={}",
            ctx.user_id,
        )
        raise HTTPException(status_code=400, detail="Invalid invitation code")
    if validation["status"] == "already_claimed":
        logger.warning(
            "invite_claim_rejected | reason=already_claimed user_id={}",
            ctx.user_id,
        )
        raise HTTPException(status_code=400, detail="Invitation code already claimed")
    row = auth_repo.claim_invitation_code(body.code, ctx.user_id)
    if row is None:
        logger.warning(
            "invite_claim_rejected | reason=claim_race user_id={}",
            ctx.user_id,
        )
        raise HTTPException(
            status_code=400,
            detail="Invitation code already claimed",
        )
    return {
        "user_type": row["user_type"],
        "invitation_code_id": str(row["id"]),
    }


class InvitationClaimForSignupRequest(BaseModel):
    """Request body for POST /auth/invitations/claim-for-signup."""

    code: str


@router.post("/claim-for-signup")
def claim_invitation_for_signup(
    request: Request,
    body: InvitationClaimForSignupRequest,
    ctx: SignupAuthContext = Depends(require_signup_managed_auth),
):
    """
    Signup orchestration: atomically claim invitation code and provision user profile.
    Single-use; deterministic errors for invalid, already-claimed, and race conditions.
    """
    if not body.code or len(body.code) != 20:
        logger.warning(
            "invite_claim_for_signup_rejected | reason=invalid_code_format user_id={}",
            ctx.user_id,
        )
        raise HTTPException(status_code=400, detail="Invalid invitation code")
    auth_repo = request.app.state.supabase_auth_repository
    validation = auth_repo.validate_invitation_code(body.code)
    if validation["status"] == "invalid":
        logger.warning(
            "invite_claim_for_signup_rejected | reason=invalid_code user_id={}",
            ctx.user_id,
        )
        raise HTTPException(status_code=400, detail="Invalid invitation code")
    if validation["status"] == "already_claimed":
        logger.warning(
            "invite_claim_for_signup_rejected | reason=already_claimed user_id={}",
            ctx.user_id,
        )
        raise HTTPException(status_code=400, detail="Invitation code already claimed")
    row = auth_repo.claim_invitation_code_for_signup(body.code, ctx.user_id)
    if row is None:
        logger.warning(
            "invite_claim_for_signup_rejected | reason=claim_race user_id={}",
            ctx.user_id,
        )
        raise HTTPException(
            status_code=400,
            detail="Invitation code already claimed",
        )
    return {
        "user_type": row["user_type"],
        "invitation_code_id": str(row["id"]),
    }
