"""Signup orchestration route: validate invite before creating auth user."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.services.signup_orchestration_service import SignupOrchestrationService

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupWithInvitationRequest(BaseModel):
    """Request body for POST /auth/signup."""

    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6)
    code: str = Field(..., min_length=20, max_length=20)
    eula_version_id: UUID
    eula_accepted: bool

    @field_validator("eula_accepted")
    @classmethod
    def eula_must_be_accepted(cls, v: bool) -> bool:
        if not v:
            raise ValueError("eula_accepted must be true")
        return v


@router.post("/signup")
async def signup_with_invitation(request: Request, body: SignupWithInvitationRequest):
    """
    Signup orchestration: validate invitation code first, then create auth user,
    claim code, and provision profile. Invalid or already-claimed codes fail
    before any auth user is created.
    """
    service: SignupOrchestrationService = request.app.state.signup_orchestration_service
    try:
        result = service.signup_with_invitation(
            email=body.email,
            password=body.password,
            code=body.code.strip(),
            eula_version_id=str(body.eula_version_id),
            eula_accepted=body.eula_accepted,
        )
        return {"user_id": result["user_id"], "user_type": result["user_type"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
