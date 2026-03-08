"""Test routes for Claude and Google Places integration."""

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


@router.get("/test/googlePlacesSearch")
def google_places_search(
    request: Request,
    query: str,
    _: None = Depends(require_auth),
):
    """
    Search for places using the Google Places API.
    """
    google_places_service = request.app.state.google_places_service
    results = google_places_service.search_places(query)
    return {"query": query, "results": results}


@router.post("/test/randomLocation")
def random_location(request: Request, _: None = Depends(require_auth)):
    """
    Create a random place entry in the Places to Visit database (test-only).
    Uses schema-derived random values; does not call Claude or Google Places.
    """
    places_service = request.app.state.places_service
    entry = places_service.generate_random_entry("Places to Visit")
    return places_service.create_place(entry)
