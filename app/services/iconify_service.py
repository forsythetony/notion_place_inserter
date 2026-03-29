"""Iconify public API wrapper for icon search (no API key)."""

from __future__ import annotations

import json
from typing import Any

import httpx


class IconifyAPIError(Exception):
    """Raised when the Iconify search request fails or returns an error response."""

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


SEARCH_URL = "https://api.iconify.design/search"


def icon_id_to_svg_url(icon_id: str) -> str:
    """
    Build a public Iconify SVG URL from a search result id like ``mdi:food-ramen``.

    Pattern: ``https://api.iconify.design/{prefix}/{name}.svg``
    """
    raw = (icon_id or "").strip()
    if not raw:
        return ""
    if ":" not in raw:
        return f"https://api.iconify.design/{raw}.svg"
    prefix, name = raw.split(":", 1)
    return f"https://api.iconify.design/{prefix}/{name}.svg"


class IconifyService:
    """Wraps Iconify GET /search for resolving a top icon SVG URL."""

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=10.0)
        self._last_search_trace: dict[str, Any] | None = None

    def clear_last_search_trace(self) -> None:
        self._last_search_trace = None

    def get_last_search_trace(self) -> dict[str, Any] | None:
        return self._last_search_trace

    def search_icons(
        self,
        term: str,
        *,
        limit: int = 64,
    ) -> list[str]:
        """
        Search Iconify and return icon ids (e.g. ``mdi:food-ramen``).
        """
        if not term or not str(term).strip():
            self.clear_last_search_trace()
            return []
        self.clear_last_search_trace()
        q = str(term).strip()
        params = {"query": q, "limit": limit}
        request_log = {
            "method": "GET",
            "url": SEARCH_URL,
            "params": dict(params),
        }
        try:
            response = self._client.get(SEARCH_URL, params=params)
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
                raise IconifyAPIError(
                    "Iconify response was not valid JSON",
                    status_code=response.status_code,
                    response_body=(response.text or "")[:2000],
                ) from e
            icons = data.get("icons") if isinstance(data, dict) else None
            icon_list = list(icons) if isinstance(icons, list) else []
            out: list[str] = []
            for it in icon_list:
                if isinstance(it, str) and it.strip():
                    out.append(it.strip())
            self._last_search_trace = {
                "request": request_log,
                "response": {
                    "status_code": response.status_code,
                    "body": data,
                },
            }
            return out
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
            raise IconifyAPIError(
                f"Iconify HTTP {e.response.status_code}: {(body or str(e))[:500]}",
                status_code=e.response.status_code,
                response_body=body,
            ) from e
        except httpx.RequestError as e:
            self._last_search_trace = {
                "request": request_log,
                "response": None,
                "error": f"RequestError: {e}",
            }
            raise IconifyAPIError(f"Iconify request error: {e}") from e

    def get_first_icon_svg_url(self, term: str) -> str | None:
        """
        Search and return the public SVG URL for the first Iconify hit, or None.
        """
        ids = self.search_icons(term)
        if not ids:
            return None
        url = icon_id_to_svg_url(ids[0])
        return url if url else None
