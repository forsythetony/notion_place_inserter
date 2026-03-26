"""Auth context and dashboard bootstrap routes."""

from fastapi import APIRouter, Depends

from app.dependencies import AuthContext, require_managed_auth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/context")
async def get_auth_context(ctx: AuthContext = Depends(require_managed_auth)):
    """
    Return authenticated user context for dashboard bootstrap.
    Requires valid Supabase Bearer token and an existing user profile.
    """
    return {
        "user_id": ctx.user_id,
        "email": ctx.email,
        "user_type": ctx.user_type,
    }
