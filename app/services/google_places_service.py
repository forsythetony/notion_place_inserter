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


def _extract_neighborhood_from_components(
    components: list[dict] | None,
) -> tuple[str | None, str | None]:
    """
    Extract neighborhood from addressComponents. Uses explicit precedence:
    1. neighborhood
    2. sublocality_level_1
    3. sublocality / other sublocality_level_*
    4. administrative_area_level_3
    5. locality
    Prefers longText over shortText. Returns (text, signal_type) or (None, None).
    signal_type is one of: "neighborhood", "sublocality_level_1", "sublocality",
    "administrative_area_level_3", "locality".
    """
    if not components:
        return (None, None)

    def _text(comp: dict) -> str:
        return (comp.get("longText") or comp.get("shortText") or "").strip()

    # 1. neighborhood
    for comp in components:
        comp_types = comp.get("types") or []
        if not isinstance(comp_types, list):
            continue
        text = _text(comp)
        if text and "neighborhood" in comp_types:
            return (text, "neighborhood")

    # 2. sublocality_level_1
    for comp in components:
        comp_types = comp.get("types") or []
        if not isinstance(comp_types, list):
            continue
        text = _text(comp)
        if text and "sublocality_level_1" in comp_types:
            return (text, "sublocality_level_1")

    # 3. sublocality / other sublocality_level_*
    for comp in components:
        comp_types = comp.get("types") or []
        if not isinstance(comp_types, list):
            continue
        text = _text(comp)
        if not text:
            continue
        if "sublocality" in comp_types or any(
            t.startswith("sublocality_level_") for t in comp_types
        ):
            return (text, "sublocality")

    # 4. administrative_area_level_3
    for comp in components:
        comp_types = comp.get("types") or []
        if not isinstance(comp_types, list):
            continue
        text = _text(comp)
        if text and "administrative_area_level_3" in comp_types:
            return (text, "administrative_area_level_3")

    # 5. locality
    for comp in components:
        comp_types = comp.get("types") or []
        if not isinstance(comp_types, list):
            continue
        text = _text(comp)
        if text and "locality" in comp_types:
            return (text, "locality")
    return (None, None)


def _extract_neighborhood_debug_signals(components: list[dict] | None) -> list[dict]:
    """
    Extract neighborhood-related address component diagnostics for debug logging.
    Returns a list of dicts with text, types, and source for each component that
    may inform neighborhood resolution (neighborhood, sublocality, sublocality_level_*,
    administrative_area_level_3, locality).
    """
    if not components:
        return []
    signals: list[dict] = []
    for comp in components:
        comp_types = comp.get("types") or []
        if not isinstance(comp_types, list):
            continue
        text = (comp.get("longText") or comp.get("shortText") or "").strip()
        if not text:
            continue
        neighborhood_types = [
            "neighborhood",
            "sublocality",
            "administrative_area_level_3",
            "locality",
        ]
        sublocality_levels = [t for t in comp_types if t.startswith("sublocality_level_")]
        if (
            any(t in comp_types for t in neighborhood_types)
            or sublocality_levels
        ):
            signals.append({
                "text": text,
                "types": comp_types,
                "source": "addressComponents",
            })
    return signals


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

    def search_places(
        self, query: str, *, return_raw_response: bool = False
    ) -> list[dict] | tuple[list[dict], dict]:
        """
        Search for places using the given text query.
        Returns a list of place dicts with displayName, formattedAddress, id, rating,
        websiteUri, googleMapsUri, generativeSummary (when available), etc.
        When return_raw_response=True, returns (normalized_list, raw_api_response).
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
        normalized = [self._normalize_place(p) for p in places_raw]
        if return_raw_response:
            return (normalized, data)
        return normalized

    def get_place_details(
        self,
        place_id: str,
        field_mask: str | None = None,
        *,
        return_raw_response: bool = False,
    ) -> dict | None | tuple[dict | None, dict | None]:
        """
        Fetch place details by ID. Used to enrich search results with editorialSummary,
        generativeSummary, and other narrative fields not always present in search.
        When return_raw_response=True, returns (normalized_place, raw_api_response).
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
        normalized = self._normalize_place(data)
        if return_raw_response:
            return (normalized, data)
        return normalized

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
        neighborhood, neighborhood_signal_type = _extract_neighborhood_from_components(
            address_components
        )
        google_neighborhood_signals = _extract_neighborhood_debug_signals(address_components)

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
            "neighborhood_signal_type": neighborhood_signal_type,
            "google_neighborhood_signals": google_neighborhood_signals,
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
