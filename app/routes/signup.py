"""Signup orchestration route: validate invite before creating auth user."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.signup_orchestration_service import SignupOrchestrationService

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupWithInvitationRequest(BaseModel):
    """Request body for POST /auth/signup."""

    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6)
    code: str = Field(..., min_length=20, max_length=20)


@router.post("/signup")
def signup_with_invitation(request: Request, body: SignupWithInvitationRequest):
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
        )
        return {"user_id": result["user_id"], "user_type": result["user_type"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
