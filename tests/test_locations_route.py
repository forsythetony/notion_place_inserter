"""Unit tests for POST /locations route (sync and async modes)."""

import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _ensure_async_disabled(client):
    """Force sync mode for tests that expect Notion page / dry-run response."""
    orig = getattr(app.state, "locations_async_enabled", True)
    app.state.locations_async_enabled = False
    yield
    app.state.locations_async_enabled = orig


def test_post_locations_401_without_auth(client):
    """POST /locations without Authorization returns 401."""
    resp = client.post("/locations", json={"keywords": "coffee shop"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


def test_post_locations_401_invalid_auth(client):
    """POST /locations with invalid Authorization returns 401."""
    resp = client.post(
        "/locations",
        headers={"Authorization": "wrong-secret"},
        json={"keywords": "restaurant"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


def test_post_locations_400_empty_keywords(client):
    """POST /locations with empty keywords returns 400."""
    resp = client.post(
        "/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": ""},
    )
    assert resp.status_code == 400
    assert "keywords" in resp.json()["detail"].lower()


def test_post_locations_400_whitespace_keywords(client):
    """POST /locations with whitespace-only keywords returns 400."""
    resp = client.post(
        "/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "   "},
    )
    assert resp.status_code == 400


def test_post_locations_400_keywords_too_long(client):
    """POST /locations with keywords exceeding max length returns 400."""
    long_keywords = "x" * 301
    resp = client.post(
        "/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": long_keywords},
    )
    assert resp.status_code == 400
    assert "300" in resp.json()["detail"]


def test_post_locations_async_returns_accepted(client):
    """POST /locations with async enabled returns 200 accepted and job_id."""
    mock_queue_repo = MagicMock()
    mock_run_repo = MagicMock()
    mock_queue_repo.send.return_value = MagicMock(message_id=1)

    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = mock_queue_repo
    app.state.supabase_run_repository = mock_run_repo

    resp = client.post(
        "/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert "job_id" in data
    assert data["job_id"].startswith("loc_")

    mock_run_repo.create_job.assert_called_once()
    call_kw = mock_run_repo.create_job.call_args[1]
    assert call_kw["keywords"] == "park"
    assert call_kw["status"] == "queued"
    assert call_kw["job_id"].startswith("loc_")

    mock_run_repo.create_run.assert_called_once()
    call_kw = mock_run_repo.create_run.call_args[1]
    assert call_kw["status"] == "pending"
    assert "job_id" in call_kw
    assert "run_id" in call_kw

    mock_queue_repo.send.assert_called_once()
    call_args = mock_queue_repo.send.call_args
    payload = call_args[0][0]
    assert payload["keywords"] == "park"
    assert payload["job_id"].startswith("loc_")
    assert "run_id" in payload
    assert call_args[1]["delay_seconds"] == 0


def test_post_locations_async_503_when_repos_unavailable(client):
    """POST /locations with async enabled but Supabase repos missing returns 503."""
    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = None
    app.state.supabase_run_repository = MagicMock()

    resp = client.post(
        "/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 503
    assert "enqueue" in resp.json()["detail"].lower()


def test_post_locations_async_503_when_run_repo_unavailable(client):
    """POST /locations with async enabled but run repo missing returns 503."""
    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = MagicMock()
    app.state.supabase_run_repository = None

    resp = client.post(
        "/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 503
    assert "enqueue" in resp.json()["detail"].lower()


def test_post_locations_async_503_when_send_raises(client):
    """POST /locations with async enabled but queue send raises returns 503."""
    mock_queue_repo = MagicMock()
    mock_queue_repo.send.side_effect = RuntimeError("pgmq unavailable")
    mock_run_repo = MagicMock()

    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = mock_queue_repo
    app.state.supabase_run_repository = mock_run_repo

    resp = client.post(
        "/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 503
    assert "enqueue" in resp.json()["detail"].lower()
