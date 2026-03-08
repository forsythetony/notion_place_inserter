"""Freepik Icons API service wrapper for icon search."""

import httpx


class FreepikService:
    """Wraps the Freepik Icons API for searching icons by term."""

    SEARCH_URL = "https://api.freepik.com/v1/icons"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = httpx.Client(timeout=10.0)

    def search_icons(
        self,
        term: str,
        *,
        page: int = 1,
        per_page: int = 1,
        order: str = "relevance",
        thumbnail_size: int = 128,
    ) -> list[dict]:
        """
        Search for icons by term. Returns a list of icon dicts.
        Uses GET /v1/icons with x-freepik-api-key header.
        """
        if not term or not str(term).strip():
            return []
        try:
            headers = {
                "x-freepik-api-key": self._api_key,
                "Accept-Language": "en-US",
            }
            params = {
                "term": str(term).strip(),
                "page": page,
                "per_page": per_page,
                "order": order,
                "thumbnail_size": thumbnail_size,
            }
            response = self._client.get(
                self.SEARCH_URL,
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            icons = data.get("data") or []
            return list(icons) if isinstance(icons, list) else []
        except Exception:
            return []

    def get_first_icon_url(self, term: str) -> str | None:
        """
        Search for icons and return the URL of the first result's thumbnail.
        Returns None when no results or no usable URL.
        """
        icons = self.search_icons(term)
        if not icons:
            return None
        first = icons[0]
        if not isinstance(first, dict):
            return None
        thumbnails = first.get("thumbnails") or []
        valid = [
            t for t in thumbnails if isinstance(t, dict) and (t.get("url") or "").strip()
        ]
        if valid:
            # Prefer largest thumbnail for quality
            best = max(valid, key=lambda t: t.get("width", 0) or t.get("height", 0))
            return (best.get("url") or "").strip() or None

        # Fallback: Freepik payloads can vary across endpoints/plans.
        return self._find_url_recursive(first)

    def _find_url_recursive(self, node: object) -> str | None:
        """Depth-first URL extraction fallback for variable API payloads."""
        if isinstance(node, dict):
            url = node.get("url")
            if isinstance(url, str):
                url = url.strip()
                if url.startswith(("http://", "https://")):
                    return url
            for value in node.values():
                found = self._find_url_recursive(value)
                if found:
                    return found
            return None
        if isinstance(node, list):
            for item in node:
                found = self._find_url_recursive(item)
                if found:
                    return found
            return None
        return None
