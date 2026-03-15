"""Unit tests for POST /triggers/{user_id}/{path} route (sync and async modes)."""

import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from loguru import logger

from app.main import app
from app.services.job_definition_service import ResolvedJobSnapshot


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


def test_post_triggers_401_without_auth(client):
    """POST /triggers/{user_id}/locations without Authorization returns 401."""
    resp = client.post(
        "/triggers/bootstrap/locations",
        json={"keywords": "coffee shop"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


def test_post_triggers_401_invalid_auth(client):
    """POST /triggers/{user_id}/locations with invalid Authorization returns 401."""
    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": "wrong-secret"},
        json={"keywords": "restaurant"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


def test_post_triggers_400_empty_keywords(client):
    """POST /triggers/{user_id}/locations with empty keywords returns 400."""
    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": ""},
    )
    assert resp.status_code == 400
    assert "keywords" in resp.json()["detail"].lower()


def test_post_triggers_400_whitespace_keywords(client):
    """POST /triggers/{user_id}/locations with whitespace-only keywords returns 400."""
    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "   "},
    )
    assert resp.status_code == 400


def test_post_triggers_400_keywords_too_long(client):
    """POST /triggers/{user_id}/locations with keywords exceeding max length returns 400."""
    long_keywords = "x" * 301
    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": long_keywords},
    )
    assert resp.status_code == 400
    assert "300" in resp.json()["detail"]


def _mock_snapshot():
    """Return a ResolvedJobSnapshot for route tests."""
    return ResolvedJobSnapshot(
        snapshot_ref="job_snapshot:bootstrap:job_notion_place_inserter:abc123",
        snapshot={"job": {"id": "job_notion_place_inserter"}},
    )


def test_post_triggers_async_returns_accepted(client):
    """POST /triggers/{user_id}/locations with async enabled returns 200 accepted and job_id."""
    mock_queue_repo = MagicMock()
    mock_run_repo = MagicMock()
    mock_job_definition_service = MagicMock()
    mock_trigger_service = MagicMock()
    mock_trigger = MagicMock(job_id="job_notion_place_inserter", owner_user_id="bootstrap")
    mock_trigger_service.resolve_by_path.return_value = mock_trigger
    mock_job_definition_service.resolve_for_run.return_value = _mock_snapshot()
    mock_queue_repo.send.return_value = MagicMock(message_id=1)

    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = mock_queue_repo
    app.state.supabase_run_repository = mock_run_repo
    app.state.job_definition_service = mock_job_definition_service
    app.state.trigger_service = mock_trigger_service

    resp = client.post(
        "/triggers/bootstrap/locations",
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
    assert call_kw["owner_user_id"] == "bootstrap"
    assert "run_id" in call_kw
    assert call_kw.get("job_definition_id") == "job_notion_place_inserter"
    assert call_kw.get("definition_snapshot_ref") == "job_snapshot:bootstrap:job_notion_place_inserter:abc123"

    mock_queue_repo.send.assert_called_once()
    call_args = mock_queue_repo.send.call_args
    payload = call_args[0][0]
    assert payload["keywords"] == "park"
    assert payload["job_id"].startswith("loc_")
    assert "run_id" in payload
    assert payload.get("job_definition_id") == "job_notion_place_inserter"
    assert payload.get("job_slug") == "notion_place_inserter"
    assert payload.get("definition_snapshot_ref") == "job_snapshot:bootstrap:job_notion_place_inserter:abc123"
    assert call_args[1]["delay_seconds"] == 0


def test_post_triggers_async_503_when_job_definition_service_unavailable(client):
    """POST /triggers/{user_id}/locations with async enabled but job_definition_service missing returns 503."""
    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = MagicMock()
    app.state.supabase_run_repository = MagicMock()
    app.state.job_definition_service = None
    app.state.trigger_service = MagicMock()

    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 503
    assert "enqueue" in resp.json()["detail"].lower()


def test_post_triggers_async_503_when_trigger_unavailable(client):
    """POST /triggers/{user_id}/locations when trigger cannot be resolved returns 503."""
    mock_queue_repo = MagicMock()
    mock_run_repo = MagicMock()
    mock_job_definition_service = MagicMock()
    mock_trigger_service = MagicMock()
    mock_trigger_service.resolve_by_path.return_value = None

    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = mock_queue_repo
    app.state.supabase_run_repository = mock_run_repo
    app.state.job_definition_service = mock_job_definition_service
    app.state.trigger_service = mock_trigger_service

    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 503
    assert "Trigger" in resp.json()["detail"] or "trigger" in resp.json()["detail"].lower()
    mock_queue_repo.send.assert_not_called()


def test_post_triggers_async_503_when_job_unavailable(client):
    """POST /triggers/{user_id}/locations when job resolution returns None returns 503."""
    mock_queue_repo = MagicMock()
    mock_run_repo = MagicMock()
    mock_job_definition_service = MagicMock()
    mock_trigger_service = MagicMock()
    mock_trigger = MagicMock(job_id="job_notion_place_inserter", owner_user_id="bootstrap")
    mock_trigger_service.resolve_by_path.return_value = mock_trigger
    mock_job_definition_service.resolve_for_run.return_value = None

    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = mock_queue_repo
    app.state.supabase_run_repository = mock_run_repo
    app.state.job_definition_service = mock_job_definition_service
    app.state.trigger_service = mock_trigger_service

    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 503
    assert "Bootstrap" in resp.json()["detail"] or "job" in resp.json()["detail"].lower()
    mock_queue_repo.send.assert_not_called()


def test_post_triggers_async_503_when_trigger_service_unavailable(client):
    """POST /triggers/{user_id}/locations with async enabled but trigger service missing returns 503."""
    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = MagicMock()
    app.state.supabase_run_repository = MagicMock()
    app.state.job_definition_service = MagicMock()
    app.state.trigger_service = None

    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 503
    assert "enqueue" in resp.json()["detail"].lower()


def test_post_legacy_locations_returns_404(client):
    """Legacy POST /locations is removed; returns 404."""
    resp = client.post(
        "/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 404


def test_post_triggers_async_503_when_repos_unavailable(client):
    """POST /triggers/{user_id}/locations with async enabled but Supabase repos missing returns 503."""
    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = None
    app.state.supabase_run_repository = MagicMock()
    # job_definition_service and trigger_service stay from lifespan

    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 503
    assert "enqueue" in resp.json()["detail"].lower()


def test_post_triggers_async_503_when_run_repo_unavailable(client):
    """POST /triggers/{user_id}/locations with async enabled but run repo missing returns 503."""
    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = MagicMock()
    app.state.supabase_run_repository = None

    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 503
    assert "enqueue" in resp.json()["detail"].lower()


def test_post_triggers_async_503_when_send_raises(client):
    """POST /triggers/{user_id}/locations with async enabled but queue send raises returns 503."""
    mock_queue_repo = MagicMock()
    mock_queue_repo.send.side_effect = RuntimeError("pgmq unavailable")
    mock_run_repo = MagicMock()
    mock_job_definition_service = MagicMock()
    mock_trigger_service = MagicMock()
    mock_trigger = MagicMock(job_id="job_notion_place_inserter", owner_user_id="bootstrap")
    mock_trigger_service.resolve_by_path.return_value = mock_trigger
    mock_job_definition_service.resolve_for_run.return_value = _mock_snapshot()

    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = mock_queue_repo
    app.state.supabase_run_repository = mock_run_repo
    app.state.job_definition_service = mock_job_definition_service
    app.state.trigger_service = mock_trigger_service

    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 503
    assert "enqueue" in resp.json()["detail"].lower()


def test_post_triggers_async_503_when_create_job_raises(client):
    """POST /triggers/{user_id}/locations when create_job raises returns 503; send is never called."""
    mock_queue_repo = MagicMock()
    mock_run_repo = MagicMock()
    mock_run_repo.create_job.side_effect = RuntimeError("Supabase unavailable")
    mock_job_definition_service = MagicMock()
    mock_trigger_service = MagicMock()
    mock_trigger = MagicMock(job_id="job_notion_place_inserter", owner_user_id="bootstrap")
    mock_trigger_service.resolve_by_path.return_value = mock_trigger
    mock_job_definition_service.resolve_for_run.return_value = _mock_snapshot()

    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = mock_queue_repo
    app.state.supabase_run_repository = mock_run_repo
    app.state.job_definition_service = mock_job_definition_service
    app.state.trigger_service = mock_trigger_service

    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 503
    mock_run_repo.create_job.assert_called_once()
    mock_queue_repo.send.assert_not_called()


def test_post_triggers_async_503_when_create_run_raises(client):
    """POST /triggers/{user_id}/locations when create_job (run persistence) raises returns 503; send is never called."""
    mock_queue_repo = MagicMock()
    mock_run_repo = MagicMock()
    mock_run_repo.create_job.side_effect = RuntimeError("Run persistence unavailable")
    mock_job_definition_service = MagicMock()
    mock_trigger_service = MagicMock()
    mock_trigger = MagicMock(job_id="job_notion_place_inserter", owner_user_id="bootstrap")
    mock_trigger_service.resolve_by_path.return_value = mock_trigger
    mock_job_definition_service.resolve_for_run.return_value = _mock_snapshot()

    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = mock_queue_repo
    app.state.supabase_run_repository = mock_run_repo
    app.state.job_definition_service = mock_job_definition_service
    app.state.trigger_service = mock_trigger_service

    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 503
    mock_run_repo.create_job.assert_called_once()
    mock_queue_repo.send.assert_not_called()


@pytest.fixture
def captured_logs():
    """Capture loguru output for assertions."""
    output = []

    def sink(message):
        record = message.record
        output.append({"message": record["message"]})

    handler_id = logger.add(sink, level="DEBUG", format="{message}")
    yield output
    logger.remove(handler_id)


def test_post_triggers_async_logs_correlation_on_success(client, captured_logs):
    """Enqueue success logs include job_id and run_id for correlation."""
    mock_queue_repo = MagicMock()
    mock_queue_repo.send.return_value = MagicMock(message_id=1)
    mock_run_repo = MagicMock()
    mock_job_definition_service = MagicMock()
    mock_trigger_service = MagicMock()
    mock_trigger = MagicMock(job_id="job_notion_place_inserter", owner_user_id="bootstrap")
    mock_trigger_service.resolve_by_path.return_value = mock_trigger
    mock_job_definition_service.resolve_for_run.return_value = _mock_snapshot()

    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = mock_queue_repo
    app.state.supabase_run_repository = mock_run_repo
    app.state.job_definition_service = mock_job_definition_service
    app.state.trigger_service = mock_trigger_service

    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    run_id = mock_run_repo.create_job.call_args[1]["run_id"]

    enqueued = next((e for e in captured_logs if "locations_enqueued" in e["message"]), None)
    assert enqueued is not None
    assert job_id in enqueued["message"]
    assert run_id in enqueued["message"]


def test_post_triggers_async_logs_correlation_on_failure(client, captured_logs):
    """Enqueue failure logs include job_id and run_id for correlation."""
    mock_queue_repo = MagicMock()
    mock_queue_repo.send.side_effect = RuntimeError("pgmq down")
    mock_run_repo = MagicMock()
    mock_job_definition_service = MagicMock()
    mock_trigger_service = MagicMock()
    mock_trigger = MagicMock(job_id="job_notion_place_inserter", owner_user_id="bootstrap")
    mock_trigger_service.resolve_by_path.return_value = mock_trigger
    mock_job_definition_service.resolve_for_run.return_value = _mock_snapshot()

    app.state.locations_async_enabled = True
    app.state.supabase_queue_repository = mock_queue_repo
    app.state.supabase_run_repository = mock_run_repo
    app.state.job_definition_service = mock_job_definition_service
    app.state.trigger_service = mock_trigger_service

    resp = client.post(
        "/triggers/bootstrap/locations",
        headers={"Authorization": os.environ.get("SECRET", "dev-secret")},
        json={"keywords": "park"},
    )
    assert resp.status_code == 503
    job_id = mock_run_repo.create_job.call_args[1]["job_id"]
    run_id = mock_run_repo.create_job.call_args[1]["run_id"]

    failed = next((e for e in captured_logs if "locations_enqueue_failed" in e["message"]), None)
    assert failed is not None
    assert job_id in failed["message"]
    assert run_id in failed["message"]
