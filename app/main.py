"""FastAPI application with secret-based authorization."""

import hmac
import os

from fastapi import FastAPI, Header, HTTPException
from loguru import logger

app = FastAPI(title="Hello World API")

SECRET = os.environ.get("secret", "")


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
