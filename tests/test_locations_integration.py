"""Integration tests for /locations and /test endpoints. Uses real server if running."""

import os

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("envs/local.env")

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
SECRET = os.environ.get("SECRET", "dev-secret")


def _assert_location_response(data: dict) -> None:
    """Assert response is either a Notion page or a dry-run preview."""
    if data.get("mode") == "dry_run":
        assert data.get("database") == "Places to Visit"
        assert "properties" in data
        assert "summary" in data
        assert "property_count" in data["summary"]
        assert "property_names" in data["summary"]
    else:
        assert data.get("object") == "page"
        assert "id" in data


@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION"),
    reason="Set RUN_INTEGRATION=1 to run (requires server)",
)
def test_post_locations_returns_page():
    """POST /locations with keywords returns 200 and Notion page or dry-run preview."""
    resp = requests.post(
        f"{BASE_URL}/locations",
        headers={"Authorization": SECRET},
        json={"keywords": "stone arch bridge minneapolis"},
        timeout=30,
    )
    assert resp.status_code == 200
    _assert_location_response(resp.json())


@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION"),
    reason="Set RUN_INTEGRATION=1 to run (requires server)",
)
def test_post_test_random_location_returns_page():
    """POST /test/randomLocation returns 200 and Notion page or dry-run preview."""
    resp = requests.post(
        f"{BASE_URL}/test/randomLocation",
        headers={"Authorization": SECRET},
        timeout=30,
    )
    assert resp.status_code == 200
    _assert_location_response(resp.json())
