"""Live connector test: isolated Notion write step.

Run with: pytest tests/test_notion_write_step_live.py -m live_notion -q

Requires env vars:
  - NOTION_API_KEY
  - NOTION_TEST_DATA_SOURCE_ID (e.g. 1e2a5cd4-f107-490f-9b7a-4af865fd1beb)
"""

import os
from datetime import datetime, timezone

import pytest

from app.services.notion_service import NotionService


@pytest.mark.live_notion
def test_notion_write_step_live():
    """Create a minimal page via NotionService.create_page to debug connector in isolation."""
    api_key = os.environ.get("NOTION_API_KEY")
    # data_source_id = os.environ.get("NOTION_TEST_DATA_SOURCE_ID")
    data_source_id = "1e2a5cd4-f107-490f-9b7a-4af865fd1beb"

    if not api_key:
        pytest.skip("NOTION_API_KEY not set; skip live Notion write test")
    if not data_source_id:
        pytest.skip("NOTION_TEST_DATA_SOURCE_ID not set; skip live Notion write test")

    svc = NotionService(api_key=api_key)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    title = f"connector-test-notion-write-{ts}"

    # Minimal Notion API payload: title property
    properties = {
        "Name": {"title": [{"text": {"content": title}}]},
    }

    result = svc.create_page(
        data_source_id=data_source_id,
        properties=properties,
    )

    assert result is not None
    assert "id" in result
    assert result.get("object") == "page"
    page_id = result["id"]
    print(f"\nconnector_test_created_page | page_id={page_id} title={title}")
    assert page_id
