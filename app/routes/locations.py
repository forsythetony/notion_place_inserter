"""Locations API routes."""

from fastapi import APIRouter, Depends, Request
from loguru import logger
from pydantic import BaseModel

from app.dependencies import require_auth

router = APIRouter()


class LocationRequest(BaseModel):
    """Request body for POST /locations."""

    keywords: str


@router.post("/locations")
def create_location(request: Request, body: LocationRequest, _: None = Depends(require_auth)):
    """
    Create a random place entry in the Places to Visit database.
    Keywords are accepted but not yet used.
    """
    location_service: "LocationService" = request.app.state.location_service

    entry = location_service.generate_random_entry("Places to Visit")
    logger.info("Generated random entry: {}", entry)

    created = location_service.create_location(entry)
    return created
