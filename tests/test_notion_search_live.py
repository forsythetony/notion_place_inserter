"""Live connector test: inspect Notion search results by title.

Run with:
  pytest tests/test_notion_search_live.py -m live_notion -q -s

Requires env vars:
  - NOTION_API_KEY
Optional env vars:
  - NOTION_SEARCH_QUERY (default: "Places to Visit")
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from app.services.notion_service import NotionService


def _extract_title(result: dict[str, Any]) -> str:
    """Best-effort title extraction across Notion object types."""
    title_rich = result.get("title")
    if isinstance(title_rich, list) and title_rich:
        title = "".join(str(t.get("plain_text", "")) for t in title_rich if isinstance(t, dict))
        if title.strip():
            return title

    props = result.get("properties")
    if isinstance(props, dict):
        for prop in props.values():
            if not isinstance(prop, dict):
                continue
            if prop.get("type") == "title":
                title_arr = prop.get("title") or []
                if isinstance(title_arr, list):
                    title = "".join(
                        str(t.get("plain_text", "")) for t in title_arr if isinstance(t, dict)
                    )
                    if title.strip():
                        return title

    return "<no-title-found>"


@pytest.mark.live_notion
def test_notion_search_places_to_visit_live() -> None:
    """Query Notion search and print raw response for manual inspection."""
    api_key = os.environ.get("NOTION_API_KEY")
    query = os.environ.get("NOTION_SEARCH_QUERY", "Places to Visit")

    if not api_key:
        pytest.skip("NOTION_API_KEY not set; skip live Notion search test")

    svc = NotionService(api_key=api_key)
    response = svc.client.search(query=query)
    results = response.get("results", []) if isinstance(response, dict) else []

    print(f"\nnotion_search_query={query!r} results_count={len(results)}")
    for idx, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue
        obj = item.get("object", "<unknown>")
        rid = item.get("id", "<no-id>")
        title = _extract_title(item)
        url = item.get("url", "<no-url>")
        print(f"[{idx}] object={obj} id={rid} title={title!r} url={url}")

    print("\nraw_notion_search_response:")
    print(json.dumps(response, indent=2, sort_keys=True, default=str))

    assert isinstance(response, dict)
    assert "results" in response
