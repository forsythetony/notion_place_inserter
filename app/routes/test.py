"""Test routes for Claude integration."""

from fastapi import APIRouter, Depends, Request

from app.dependencies import require_auth

router = APIRouter()


@router.get("/test/claude")
def claude_poem(
    request: Request,
    poem_seed: str = "sunset",
    _: None = Depends(require_auth),
):
    """
    Generate a poem using Claude, inspired by the given seed.
    """
    claude_service = request.app.state.claude_service
    poem = claude_service.write_poem(poem_seed)
    return {"poem": poem}
