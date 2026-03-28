"""Freepik Icons API service wrapper for icon search."""

import json
from typing import Any

import httpx


class FreepikAPIError(Exception):
    """Raised when the Freepik Icons API request fails or returns an error response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


# Stopgap: we have been IP-blocked on Freepik icon search. Until we wire a stable icon provider,
# queries containing "ramen" skip the API and use this hosted asset instead.
RAMEN_ICON_STOPGAP_URL = (
    "https://s3.oleo.sh/static/84894e1482ad25671b475a5a8cdee88667b01c04b0cc936e5c73035cf1c2d04a.png"
)


def is_ramen_icon_stopgap(term: str) -> bool:
    """True when the search term should use RAMEN_ICON_STOPGAP_URL instead of Freepik."""
    if not term or not isinstance(term, str):
        return False
    return "ramen" in term.strip().lower()


def _mask_freepik_api_key(api_key: str) -> str:
    """Log-safe API key fingerprint (same idea as other integration logs)."""
    k = api_key or ""
    if not k:
        return "[unset]"
    if len(k) <= 12:
        return "…(redacted)…"
    return f"{k[:4]}…(redacted,len={len(k)})…{k[-4:]}"


class FreepikService:
    """Wraps the Freepik Icons API for searching icons by term."""

    SEARCH_URL = "https://api.freepik.com/v1/icons"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = httpx.Client(timeout=10.0)
        self._last_search_trace: dict[str, Any] | None = None

    def clear_last_search_trace(self) -> None:
        """Reset before a search; avoids stale traces when reusing the client."""
        self._last_search_trace = None

    def get_last_search_trace(self) -> dict[str, Any] | None:
        """Last GET /v1/icons request/response snapshot for step processing logs."""
        return self._last_search_trace

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
            self.clear_last_search_trace()
            return []
        self.clear_last_search_trace()
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
        request_log = {
            "method": "GET",
            "url": self.SEARCH_URL,
            "params": dict(params),
            "headers": {
                "x-freepik-api-key": _mask_freepik_api_key(self._api_key),
                "Accept-Language": headers["Accept-Language"],
            },
        }
        try:
            response = self._client.get(
                self.SEARCH_URL,
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                raw_text = response.text or ""
                self._last_search_trace = {
                    "request": request_log,
                    "response": {
                        "status_code": response.status_code,
                        "body_text": raw_text,
                    },
                    "error": f"JSONDecodeError: {e}",
                }
                raise FreepikAPIError(
                    "Freepik response was not valid JSON",
                    status_code=response.status_code,
                    response_body=(response.text or "")[:2000],
                ) from e
            icons = data.get("data") or []
            icon_list = list(icons) if isinstance(icons, list) else []
            self._last_search_trace = {
                "request": request_log,
                "response": {
                    "status_code": response.status_code,
                    "body": data,
                },
            }
            return icon_list
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = (e.response.text or "")[:50000]
            except Exception:
                pass
            self._last_search_trace = {
                "request": request_log,
                "response": {
                    "status_code": e.response.status_code,
                    "body_text": body,
                },
                "error": "HTTPStatusError",
            }
            raise FreepikAPIError(
                f"Freepik HTTP {e.response.status_code}: {(body or str(e))[:500]}",
                status_code=e.response.status_code,
                response_body=body,
            ) from e
        except httpx.RequestError as e:
            self._last_search_trace = {
                "request": request_log,
                "response": None,
                "error": f"RequestError: {e}",
            }
            raise FreepikAPIError(f"Freepik request error: {e}") from e

    def get_first_icon_url(self, term: str) -> str | None:
        """
        Search for icons and return the URL of the first result's thumbnail.
        Returns None when no results or no usable URL.
        """
        if is_ramen_icon_stopgap(term):
            self.clear_last_search_trace()
            return RAMEN_ICON_STOPGAP_URL
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
