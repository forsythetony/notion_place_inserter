"""Locations API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.dependencies import require_auth

router = APIRouter()


class LocationRequest(BaseModel):
    """Request body for POST /locations."""

    keywords: str


@router.post("/locations")
def create_location(request: Request, body: LocationRequest, _: None = Depends(require_auth)):
    """
    Create a place entry in the Places to Visit database.
    Runs pipeline (query rewrite + Google Places + property resolution).
    Keywords must be non-empty. For random test entries, use POST /test/randomLocation.
    """
    if not body.keywords.strip():
        raise HTTPException(
            status_code=400,
            detail="keywords is required and cannot be empty. Use POST /test/randomLocation for random test entries.",
        )
    places_service: "PlacesService" = request.app.state.places_service
    return places_service.create_place_from_query(body.keywords)
