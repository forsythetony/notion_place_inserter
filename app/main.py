"""FastAPI application with secret-based authorization."""

import hmac
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from loguru import logger

from app.routes import locations, test
from app.services.claude_service import ClaudeService
from app.services.location_service import LocationService
from app.services.notion_service import NotionService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    notion_key = os.environ.get("NOTION_API_KEY")
    if not notion_key:
        raise RuntimeError("NOTION_API_KEY environment variable is required")
    anthropic_token = os.environ.get("ANTHROPIC_TOKEN")
    if not anthropic_token:
        raise RuntimeError("ANTHROPIC_TOKEN environment variable is required")

    notion_svc = NotionService(api_key=notion_key)
    notion_svc.initialize()

    app.state.notion_service = notion_svc
    app.state.location_service = LocationService(notion_svc)
    app.state.claude_service = ClaudeService(api_key=anthropic_token)

    yield
    # shutdown (no cleanup needed)


app = FastAPI(title="Hello World API", lifespan=lifespan)

SECRET = os.environ.get("secret", "")

app.include_router(locations.router)
app.include_router(test.router)


@app.get("/")
def hello(authorization: str | None = Header(default=None)):
    """Return a greeting if the Authorization header matches the secret."""
    if not SECRET:
        logger.error("SECRET environment variable is not set")
        raise HTTPException(status_code=500, detail="Server misconfiguration")

    if not authorization or not hmac.compare_digest(authorization, SECRET):
        logger.warning("Unauthorized request: missing or invalid Authorization header")
        raise HTTPException(status_code=401, detail="Unauthorized")

    return {"message": "Hello there!"}
