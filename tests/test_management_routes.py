"""Unit tests for GET /management/* (dashboard list) routes."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.domain.connectors import ConnectorInstance
from app.domain.jobs import JobDefinition
from app.domain.limits import AppLimits
from app.domain.triggers import TriggerDefinition
from app.main import app
from app.services.supabase_auth_repository import USER_TYPE_STANDARD


@pytest.fixture
def client():
    return TestClient(app)


def _mock_user(id_: str, email: str | None = "user@example.com"):
    u = MagicMock()
    u.id = id_
    u.email = email
    return u


def _mock_user_response(user):
    r = MagicMock()
    r.user = user
    return r


def _setup_auth(client, user_id="550e8400-e29b-41d4-a716-446655440000"):
    """Set app.state so require_managed_auth passes."""
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.return_value = _mock_user_response(
        _mock_user(user_id, "user@example.com")
    )
    mock_auth_repo = MagicMock()
    mock_auth_repo.get_profile.return_value = {
        "user_id": user_id,
        "user_type": USER_TYPE_STANDARD,
    }
    app.state.supabase_client = mock_supabase
    app.state.supabase_auth_repository = mock_auth_repo
    return user_id


def test_management_pipelines_401_without_auth(client):
    """GET /management/pipelines without Authorization returns 401."""
    resp = client.get("/management/pipelines")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


def test_management_pipelines_401_malformed_bearer(client):
    """GET /management/pipelines with non-Bearer Authorization returns 401."""
    resp = client.get(
        "/management/pipelines",
        headers={"Authorization": "Basic foo:bar"},
    )
    assert resp.status_code == 401


def test_management_pipelines_200_list_shape(client):
    """GET /management/pipelines with valid auth returns items list."""
    user_id = _setup_auth(client)
    mock_job_repo = MagicMock()
    mock_job_repo.list_by_owner.return_value = [
        JobDefinition(
            id="job-1",
            owner_user_id=user_id,
            display_name="Notion Place Inserter",
            target_id="tgt1",
            status="active",
            stage_ids=["s1"],
            updated_at=datetime(2026, 3, 15, 12, 0, 0),
        ),
    ]
    app.state.job_repository = mock_job_repo

    resp = client.get(
        "/management/pipelines",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["id"] == "job-1"
    assert item["display_name"] == "Notion Place Inserter"
    assert item["status"] == "active"
    assert "2026-03-15" in (item["updated_at"] or "")
    mock_job_repo.list_by_owner.assert_called_once_with(user_id)


def test_management_connections_401_without_auth(client):
    """GET /management/connections without Authorization returns 401."""
    resp = client.get("/management/connections")
    assert resp.status_code == 401


def test_management_connections_200_list_shape(client):
    """GET /management/connections with valid auth returns items list."""
    user_id = _setup_auth(client)
    mock_conn_repo = MagicMock()
    mock_conn_repo.list_by_owner.return_value = [
        ConnectorInstance(
            id="conn-1",
            owner_user_id=user_id,
            connector_template_id="tpl-notion",
            display_name="My Notion",
            status="active",
            config={},
            secret_ref="env:NOTION_API_KEY",
            last_validated_at=datetime(2026, 3, 15, 10, 0, 0),
            last_error=None,
        ),
    ]
    app.state.connector_instance_repository = mock_conn_repo

    resp = client.get(
        "/management/connections",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["id"] == "conn-1"
    assert item["display_name"] == "My Notion"
    assert item["status"] == "active"
    assert item["connector_template_id"] == "tpl-notion"
    assert "2026-03-15" in (item["last_validated_at"] or "")
    assert item["last_error"] is None
    mock_conn_repo.list_by_owner.assert_called_once_with(user_id)


def test_management_triggers_401_without_auth(client):
    """GET /management/triggers without Authorization returns 401."""
    resp = client.get("/management/triggers")
    assert resp.status_code == 401


def test_management_triggers_200_list_shape(client):
    """GET /management/triggers with valid auth returns items list."""
    user_id = _setup_auth(client)
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.list_by_owner.return_value = [
        TriggerDefinition(
            id="trigger-1",
            owner_user_id=user_id,
            trigger_type="http",
            display_name="Locations",
            path="locations",
            method="POST",
            request_body_schema={"keywords": "string"},
            status="active",
            auth_mode="bearer",
            secret_value="abc123def456",
            secret_last_rotated_at=datetime(2026, 3, 15, 14, 0, 0),
            updated_at=datetime(2026, 3, 15, 14, 0, 0),
        ),
    ]
    app.state.trigger_repository = mock_trigger_repo

    resp = client.get(
        "/management/triggers",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["id"] == "trigger-1"
    assert item["display_name"] == "Locations"
    assert item["trigger_type"] == "http"
    assert item["path"] == "locations"
    assert item["method"] == "POST"
    assert item["status"] == "active"
    assert item["auth_mode"] == "bearer"
    assert "secret" in item
    assert item["secret"] == "abc123def456"
    assert "secret_last_rotated_at" in item
    assert "2026-03-15" in (item["updated_at"] or "")
    mock_trigger_repo.list_by_owner.assert_called_once_with(user_id)


def test_management_rotate_secret_200_returns_new_secret(client):
    """POST /management/triggers/{id}/rotate-secret with valid auth returns new secret."""
    from app.domain.triggers import TriggerDefinition

    user_id = _setup_auth(client)
    mock_trigger_repo = MagicMock()
    rotated_trigger = TriggerDefinition(
        id="trigger-1",
        owner_user_id=user_id,
        trigger_type="http",
        display_name="Locations",
        path="locations",
        method="POST",
        request_body_schema={},
        status="active",
        auth_mode="bearer",
        secret_value="new_secret_abc123",
        secret_last_rotated_at=datetime(2026, 3, 15, 15, 0, 0),
    )
    mock_trigger_repo.rotate_secret.return_value = (rotated_trigger, "new_secret_abc123")
    app.state.trigger_repository = mock_trigger_repo

    resp = client.post(
        "/management/triggers/trigger-1/rotate-secret",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "trigger-1"
    assert data["secret"] == "new_secret_abc123"
    assert "secret_last_rotated_at" in data
    mock_trigger_repo.rotate_secret.assert_called_once_with("trigger-1", user_id)


def test_management_rotate_secret_404_when_trigger_not_found(client):
    """POST /management/triggers/{id}/rotate-secret returns 404 when trigger not found."""
    user_id = _setup_auth(client)
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.rotate_secret.side_effect = ValueError("Trigger not found: id=missing owner=...")
    app.state.trigger_repository = mock_trigger_repo

    resp = client.post(
        "/management/triggers/missing/rotate-secret",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_management_create_trigger_401_without_auth(client):
    """POST /management/triggers without Authorization returns 401."""
    resp = client.post(
        "/management/triggers",
        json={"path": "/my-trigger"},
    )
    assert resp.status_code == 401


def test_management_create_trigger_200_returns_created_trigger(client):
    """POST /management/triggers with valid auth creates trigger and returns it with secret."""
    user_id = _setup_auth(client)
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_path.return_value = None
    app.state.trigger_repository = mock_trigger_repo

    resp = client.post(
        "/management/triggers",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"path": "my-trigger", "display_name": "My Custom Trigger"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["id"].startswith("trigger_")
    assert data["display_name"] == "My Custom Trigger"
    assert data["path"] == "/my-trigger"
    assert data["method"] == "POST"
    assert data["status"] == "active"
    assert data["auth_mode"] == "bearer"
    assert "secret" in data
    assert len(data["secret"]) >= 20
    mock_trigger_repo.get_by_path.assert_called_once()
    call_args = mock_trigger_repo.get_by_path.call_args
    assert call_args[0][0] == "/my-trigger"
    assert call_args[0][1] == user_id
    mock_trigger_repo.save.assert_called_once()
    saved_trigger = mock_trigger_repo.save.call_args[0][0]
    assert saved_trigger.request_body_schema == {"keywords": "string"}


def test_management_create_trigger_409_duplicate_path(client):
    """POST /management/triggers returns 409 when path already in use."""
    user_id = _setup_auth(client)
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_path.return_value = TriggerDefinition(
        id="existing",
        owner_user_id=user_id,
        trigger_type="http",
        display_name="Existing",
        path="/my-trigger",
        method="POST",
        request_body_schema={},
        status="active",
        auth_mode="bearer",
        secret_value="secret",
    )
    app.state.trigger_repository = mock_trigger_repo

    resp = client.post(
        "/management/triggers",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"path": "/my-trigger"},
    )
    assert resp.status_code == 409
    assert "already in use" in resp.json()["detail"]
    mock_trigger_repo.save.assert_not_called()


def test_management_create_trigger_normalizes_path(client):
    """POST /management/triggers normalizes path to leading slash."""
    _setup_auth(client)
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_path.return_value = None
    app.state.trigger_repository = mock_trigger_repo

    resp = client.post(
        "/management/triggers",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"path": "no-leading-slash"},
    )
    assert resp.status_code == 200
    assert resp.json()["path"] == "/no-leading-slash"


def test_management_account_401_without_auth(client):
    """GET /management/account without Authorization returns 401."""
    resp = client.get("/management/account")
    assert resp.status_code == 401


def test_management_account_200_without_limits(client):
    """GET /management/account with valid auth returns user context, no limits."""
    user_id = _setup_auth(client)
    app.state.app_config_repository = None

    resp = client.get(
        "/management/account",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == user_id
    assert data["email"] == "user@example.com"
    assert data["user_type"] == USER_TYPE_STANDARD
    assert "limits" not in data


def test_management_account_200_with_limits(client):
    """GET /management/account with valid auth and app_config returns limits."""
    user_id = _setup_auth(client)
    mock_app_config = MagicMock()
    mock_app_config.get_by_owner.return_value = AppLimits(
        max_stages_per_job=10,
        max_pipelines_per_stage=20,
        max_steps_per_pipeline=50,
    )
    app.state.app_config_repository = mock_app_config

    resp = client.get(
        "/management/account",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == user_id
    assert "limits" in data
    assert data["limits"]["max_stages_per_job"] == 10
    assert data["limits"]["max_pipelines_per_stage"] == 20
    assert data["limits"]["max_steps_per_pipeline"] == 50
    mock_app_config.get_by_owner.assert_called_once_with(user_id)
