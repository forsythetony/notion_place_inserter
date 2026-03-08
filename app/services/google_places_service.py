"""Google Places API service wrapper for place search and details."""

import httpx


def _extract_localized_text(obj: dict | None) -> str:
    """Extract text from a LocalizedText object (e.g. displayName, editorialSummary)."""
    if not obj:
        return ""
    if isinstance(obj, dict) and "text" in obj:
        return obj.get("text", "") or ""
    if hasattr(obj, "text"):
        return getattr(obj, "text", "") or ""
    return ""


def _extract_neighborhood_from_components(components: list[dict] | None) -> str | None:
    """
    Extract neighborhood from addressComponents. Prefers neighborhood/sublocality,
    falls back to locality for urban context. Returns None if no suitable component.
    """
    if not components:
        return None
    for comp in components:
        comp_types = comp.get("types") or []
        if not isinstance(comp_types, list):
            continue
        text = (comp.get("longText") or comp.get("shortText") or "").strip()
        if not text:
            continue
        if (
            "neighborhood" in comp_types
            or "sublocality" in comp_types
            or any(t.startswith("sublocality_level_") for t in comp_types)
        ):
            return text

    # Some places expose district-like areas through administrative levels.
    for comp in components:
        comp_types = comp.get("types") or []
        if not isinstance(comp_types, list):
            continue
        text = (comp.get("longText") or comp.get("shortText") or "").strip()
        if not text:
            continue
        if "administrative_area_level_3" in comp_types:
            return text

    for comp in components:
        comp_types = comp.get("types") or []
        if not isinstance(comp_types, list):
            continue
        text = (comp.get("longText") or comp.get("shortText") or "").strip()
        if not text:
            continue
        if "locality" in comp_types:
            return text
    return None


class GooglePlacesService:
    """Wraps the Google Places API (New) for text search and place details."""

    SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
    DETAILS_URL_TEMPLATE = "https://places.googleapis.com/v1/places/{place_id}"
    DEFAULT_FIELD_MASK = (
        "places.displayName,places.formattedAddress,places.id,places.rating,"
        "places.websiteUri,places.googleMapsUri,places.nationalPhoneNumber,places.internationalPhoneNumber,"
        "places.location,places.primaryType,places.types,places.generativeSummary,"
        "places.addressComponents,places.photos"
    )
    DETAILS_SUMMARY_FIELD_MASK = (
        "id,displayName,formattedAddress,rating,primaryType,types,"
        "generativeSummary,editorialSummary,addressComponents,photos"
    )
    PHOTO_MEDIA_URL_TEMPLATE = "https://places.googleapis.com/v1/{photo_name}"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = httpx.Client(timeout=10.0)

    def search_places(self, query: str) -> list[dict]:
        """
        Search for places using the given text query.
        Returns a list of place dicts with displayName, formattedAddress, id, rating,
        websiteUri, googleMapsUri, generativeSummary (when available), etc.
        """
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": self.DEFAULT_FIELD_MASK,
        }
        payload = {"textQuery": query}
        response = self._client.post(self.SEARCH_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        places_raw = data.get("places", [])
        return [self._normalize_place(p) for p in places_raw]

    def get_place_details(self, place_id: str, field_mask: str | None = None) -> dict | None:
        """
        Fetch place details by ID. Used to enrich search results with editorialSummary,
        generativeSummary, and other narrative fields not always present in search.
        """
        if not place_id:
            return None
        mask = field_mask or self.DETAILS_SUMMARY_FIELD_MASK
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": mask,
        }
        url = self.DETAILS_URL_TEMPLATE.format(place_id=place_id)
        response = self._client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return self._normalize_place(data)

    def _normalize_place(self, place: dict) -> dict:
        """Extract and flatten place fields for a clean response."""
        display_name = _extract_localized_text(place.get("displayName"))
        location = place.get("location") or {}
        latitude = location.get("latitude")
        longitude = location.get("longitude")

        generative_summary = ""
        gs = place.get("generativeSummary")
        if gs and isinstance(gs, dict):
            overview = gs.get("overview")
            if overview:
                generative_summary = _extract_localized_text(overview)

        editorial_summary = _extract_localized_text(place.get("editorialSummary"))
        address_components = place.get("addressComponents") or []
        neighborhood = _extract_neighborhood_from_components(address_components)

        photos_raw = place.get("photos") or []
        photos = [
            {"name": p.get("name"), "widthPx": p.get("widthPx"), "heightPx": p.get("heightPx")}
            for p in photos_raw
            if isinstance(p, dict) and p.get("name")
        ]

        return {
            "id": place.get("id", ""),
            "displayName": display_name,
            "formattedAddress": place.get("formattedAddress", ""),
            "addressComponents": address_components,
            "neighborhood": neighborhood,
            "rating": place.get("rating"),
            "websiteUri": place.get("websiteUri", ""),
            "googleMapsUri": place.get("googleMapsUri", ""),
            "nationalPhoneNumber": place.get("nationalPhoneNumber"),
            "internationalPhoneNumber": place.get("internationalPhoneNumber"),
            "latitude": latitude,
            "longitude": longitude,
            "primaryType": place.get("primaryType"),
            "types": place.get("types", []) or [],
            "generativeSummary": generative_summary or None,
            "editorialSummary": editorial_summary or None,
            "photos": photos,
        }

    def get_photo_url(
        self,
        photo_name: str,
        *,
        max_width_px: int = 1200,
        max_height_px: int | None = None,
    ) -> str | None:
        """
        Resolve a photo resource name to a temporary URL. Uses Places Photo Media API
        with skipHttpRedirect to obtain photoUri. Note: Google's photoUri URLs often
        return 400 when accessed directly (browser or Notion); prefer get_photo_bytes
        for reliable use with Notion covers.
        """
        if not photo_name or not photo_name.strip():
            return None
        media_name = photo_name.rstrip("/") + "/media" if not photo_name.endswith("/media") else photo_name
        url = self.PHOTO_MEDIA_URL_TEMPLATE.format(photo_name=media_name)
        params: dict[str, str | int] = {"key": self._api_key, "maxWidthPx": max_width_px}
        if max_height_px is not None:
            params["maxHeightPx"] = max_height_px
        params["skipHttpRedirect"] = "true"
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("photoUri") or None
        except Exception:
            return None

    def get_photo_bytes(
        self,
        photo_name: str,
        *,
        max_width_px: int = 1200,
        max_height_px: int | None = None,
    ) -> bytes | None:
        """
        Fetch image bytes directly from the Places Photo Media API. Uses the API
        endpoint with redirect following (no skipHttpRedirect), so the response
        is the raw image. This works reliably for uploading to Notion, unlike
        photoUri URLs which often fail when accessed by third parties.
        """
        if not photo_name or not photo_name.strip():
            return None
        media_name = photo_name.rstrip("/") + "/media" if not photo_name.endswith("/media") else photo_name
        url = self.PHOTO_MEDIA_URL_TEMPLATE.format(photo_name=media_name)
        params: dict[str, str | int] = {"key": self._api_key, "maxWidthPx": max_width_px}
        if max_height_px is not None:
            params["maxHeightPx"] = max_height_px
        try:
            response = self._client.get(url, params=params, follow_redirects=True)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "image" not in content_type and "octet-stream" not in content_type:
                return None
            return response.content
        except Exception:
            return None
