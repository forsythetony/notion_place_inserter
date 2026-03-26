"""Unit tests for Notion OAuth and connection lifecycle routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.domain.connectors import ConnectorInstance
from app.domain.targets import DataTarget
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
    mock_supabase.auth.get_user = AsyncMock(
        return_value=_mock_user_response(_mock_user(user_id, "user@example.com"))
    )
    mock_auth_repo = MagicMock()
    mock_auth_repo.get_profile = AsyncMock(
        return_value={
            "user_id": user_id,
            "user_type": USER_TYPE_STANDARD,
        }
    )
    app.state.supabase_client = mock_supabase
    app.state.supabase_auth_repository = mock_auth_repo
    return user_id


NOTION_CONN_ID = "connector_instance_notion_default"


@patch("app.routes.notion_oauth.is_notion_oauth_configured", return_value=True)
def test_notion_oauth_start_200_returns_url(mock_configured, client):
    """POST /management/connections/notion/oauth/start returns authorization_url."""
    user_id = _setup_auth(client)
    mock_svc = MagicMock()
    mock_svc.start_oauth = AsyncMock(
        return_value="https://api.notion.com/v1/oauth/authorize?client_id=xxx"
    )
    app.state.notion_oauth_service = mock_svc

    resp = client.post(
        "/management/connections/notion/oauth/start",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "authorization_url" in data
    assert "notion.com" in data["authorization_url"]
    mock_svc.start_oauth.assert_awaited_once_with(
        owner_user_id=user_id,
        success_redirect="http://localhost:5173/connections?connected=notion",
    )


@patch("app.routes.notion_oauth.is_notion_oauth_configured", return_value=False)
def test_notion_oauth_start_503_when_not_configured(mock_configured, client):
    """POST /management/connections/notion/oauth/start returns 503 when OAuth not configured."""
    _setup_auth(client)
    resp = client.post(
        "/management/connections/notion/oauth/start",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"].lower()


def test_notion_oauth_start_401_without_auth(client):
    """POST /management/connections/notion/oauth/start requires auth."""
    resp = client.post("/management/connections/notion/oauth/start")
    assert resp.status_code == 401


def test_disconnect_200_returns_status(client):
    """POST /management/connections/{id}/disconnect returns status."""
    user_id = _setup_auth(client)
    mock_svc = MagicMock()
    mock_svc.disconnect = AsyncMock(
        return_value=ConnectorInstance(
            id=NOTION_CONN_ID,
            owner_user_id=user_id,
            connector_template_id="notion_oauth_workspace",
            display_name="Notion",
            status="active",
            config={},
            secret_ref=None,
            auth_status="disconnected",
        )
    )
    app.state.notion_oauth_service = mock_svc

    resp = client.post(
        f"/management/connections/{NOTION_CONN_ID}/disconnect",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "disconnected"
    assert data["id"] == NOTION_CONN_ID
    mock_svc.disconnect.assert_awaited_once_with(owner_user_id=user_id)


def test_disconnect_404_for_unknown_connection(client):
    """POST /management/connections/{id}/disconnect returns 404 for non-Notion."""
    _setup_auth(client)
    resp = client.post(
        "/management/connections/connector_instance_other/disconnect",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 404


def test_refresh_sources_200_returns_sources(client):
    """POST /management/connections/{id}/refresh-sources returns summary + sources."""
    user_id = _setup_auth(client)
    mock_targets = MagicMock()
    mock_targets.list_by_connector = AsyncMock(return_value=[])
    mock_schema = MagicMock()
    mock_schema.get_fetched_at_for_snapshots = AsyncMock(return_value={})
    mock_schema.get_by_id = AsyncMock(return_value=None)
    app.state.target_repository = mock_targets
    app.state.target_schema_repository = mock_schema

    mock_svc = MagicMock()
    mock_svc.refresh_sources = AsyncMock()
    mock_ext_repo = MagicMock()
    mock_ext_repo.list_for_instance = AsyncMock(
        return_value=[
            {
                "external_source_id": "abc-123",
                "display_name": "My Database",
                "is_accessible": True,
                "last_seen_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
        ]
    )
    app.state.notion_oauth_service = mock_svc
    app.state.connector_external_sources_repository = mock_ext_repo

    resp = client.post(
        f"/management/connections/{NOTION_CONN_ID}/refresh-sources",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert data["summary"]["totalSources"] == 1
    assert "sources" in data
    assert len(data["sources"]) == 1
    assert data["sources"][0]["external_source_id"] == "abc-123"
    assert data["sources"][0]["display_name"] == "My Database"
    assert data["sources"][0]["source_refreshed_at"] is not None
    mock_svc.refresh_sources.assert_awaited_once_with(owner_user_id=user_id)
    mock_ext_repo.list_for_instance.assert_awaited_once_with(
        connector_instance_id=NOTION_CONN_ID,
        owner_user_id=user_id,
        provider="notion",
    )


def test_list_data_sources_200_returns_sources(client):
    """GET /management/connections/{id}/data-sources returns sources."""
    user_id = _setup_auth(client)
    mock_targets = MagicMock()
    mock_targets.list_by_connector = AsyncMock(return_value=[])
    mock_schema = MagicMock()
    mock_schema.get_fetched_at_for_snapshots = AsyncMock(return_value={})
    mock_schema.get_by_id = AsyncMock(return_value=None)
    app.state.target_repository = mock_targets
    app.state.target_schema_repository = mock_schema

    mock_ext_repo = MagicMock()
    mock_ext_repo.list_for_instance = AsyncMock(
        return_value=[
            {"external_source_id": "def-456", "display_name": "Places", "is_accessible": True},
        ]
    )
    app.state.connector_external_sources_repository = mock_ext_repo

    resp = client.get(
        f"/management/connections/{NOTION_CONN_ID}/data-sources",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "sources" in data
    assert len(data["sources"]) == 1
    assert data["sources"][0]["external_source_id"] == "def-456"
    mock_ext_repo.list_for_instance.assert_awaited_once_with(
        connector_instance_id=NOTION_CONN_ID,
        owner_user_id=user_id,
        provider="notion",
    )


def test_select_data_sources_200_creates_targets(client):
    """POST /management/connections/{id}/data-sources/select creates targets."""
    user_id = _setup_auth(client)
    mock_target_repo = MagicMock()
    mock_target_repo.get_by_id = AsyncMock(return_value=None)
    mock_target_repo.save = AsyncMock()
    mock_ext_repo = MagicMock()
    mock_ext_repo.list_for_instance = AsyncMock(
        return_value=[
            {"external_source_id": "src-1", "display_name": "DB1", "is_accessible": True},
        ]
    )
    app.state.target_repository = mock_target_repo
    app.state.connector_external_sources_repository = mock_ext_repo
    app.state.schema_sync_service = None

    resp = client.post(
        f"/management/connections/{NOTION_CONN_ID}/data-sources/select",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"external_source_ids": ["src-1"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "targets" in data
    assert len(data["targets"]) >= 1
    mock_target_repo.save.assert_awaited()
    saved = mock_target_repo.save.call_args[0][0]
    assert isinstance(saved, DataTarget)
    assert saved.external_target_id == "src-1"
    assert saved.connector_instance_id == NOTION_CONN_ID
