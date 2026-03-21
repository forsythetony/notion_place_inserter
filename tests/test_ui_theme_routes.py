"""Tests for GET /theme/runtime and /management/ui-theme/*."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.supabase_auth_repository import USER_TYPE_ADMIN, USER_TYPE_STANDARD


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


def _setup_auth(client, *, user_id="550e8400-e29b-41d4-a716-446655440000", user_type=USER_TYPE_STANDARD):
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.return_value = _mock_user_response(_mock_user(user_id))
    mock_auth_repo = MagicMock()
    mock_auth_repo.get_profile.return_value = {
        "user_id": user_id,
        "user_type": user_type,
    }
    app.state.supabase_client = mock_supabase
    app.state.supabase_auth_repository = mock_auth_repo
    return user_id


def _valid_config():
    return {
        "schemaVersion": 1,
        "tokens": {
            "color": {"primary": "#111111", "text": "#eeeeee"},
            "radius": {"buttonPrimary": "8px"},
        },
    }


def test_theme_runtime_401_without_auth(client):
    resp = client.get("/theme/runtime")
    assert resp.status_code == 401


def test_theme_runtime_200_mock_service(client):
    _setup_auth(client)
    mock_svc = MagicMock()
    mock_svc.get_runtime_payload.return_value = {
        "schemaVersion": 1,
        "presetId": None,
        "cssVars": {"--pipeliner-color-primary": "#7AA2F7"},
    }
    app.state.ui_theme_service = mock_svc
    resp = client.get("/theme/runtime", headers={"Authorization": "Bearer token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["schemaVersion"] == 1
    assert data["cssVars"]["--pipeliner-color-primary"] == "#7AA2F7"
    mock_svc.get_runtime_payload.assert_called_once()


def test_ui_theme_presets_403_non_admin(client):
    _setup_auth(client, user_type=USER_TYPE_STANDARD)
    resp = client.get("/management/ui-theme/presets", headers={"Authorization": "Bearer t"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin access required"


def test_ui_theme_presets_200_admin(client):
    _setup_auth(client, user_type=USER_TYPE_ADMIN)
    mock_repo = MagicMock()
    mock_repo.list_presets_metadata.return_value = [
        {
            "id": "pid-1",
            "name": "Default",
            "is_system": True,
            "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        }
    ]
    mock_svc = MagicMock()
    mock_svc._repo = mock_repo
    app.state.ui_theme_service = mock_svc
    resp = client.get("/management/ui-theme/presets", headers={"Authorization": "Bearer t"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == "pid-1"
    assert items[0]["isSystem"] is True


def test_ui_theme_delete_system_403(client):
    _setup_auth(client, user_type=USER_TYPE_ADMIN)
    mock_repo = MagicMock()
    mock_repo.get_preset_is_system.return_value = True
    mock_svc = MagicMock()
    mock_svc._repo = mock_repo
    app.state.ui_theme_service = mock_svc
    resp = client.delete(
        "/management/ui-theme/presets/a0000001-0000-4000-8000-000000000001",
        headers={"Authorization": "Bearer t"},
    )
    assert resp.status_code == 403


def test_ui_theme_create_422_invalid_config(client):
    _setup_auth(client, user_type=USER_TYPE_ADMIN)
    mock_repo = MagicMock()
    mock_svc = MagicMock()
    mock_svc._repo = mock_repo
    app.state.ui_theme_service = mock_svc
    resp = client.post(
        "/management/ui-theme/presets",
        headers={"Authorization": "Bearer t"},
        json={"name": "Bad", "config": {"schemaVersion": 1, "tokens": {"color": {"primary": 123}}}},
    )
    assert resp.status_code == 422
    assert "validation_errors" in resp.json()


def test_ui_theme_preview_derived_admin(client):
    _setup_auth(client, user_type=USER_TYPE_ADMIN)
    mock_svc = MagicMock()
    mock_svc.preview_derived_config.return_value = {
        "schemaVersion": 1,
        "tokens": {"color": {"surface": "#111318"}},
    }
    app.state.ui_theme_service = mock_svc
    resp = client.post(
        "/management/ui-theme/actions/preview-derived",
        headers={"Authorization": "Bearer t"},
        json={
            "baseConfig": _valid_config(),
            "target": "dark",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["config"]["schemaVersion"] == 1


def test_ui_theme_set_active_404_unknown_preset(client):
    _setup_auth(client, user_type=USER_TYPE_ADMIN)
    mock_repo = MagicMock()
    mock_repo.get_preset_by_id.return_value = None
    mock_svc = MagicMock()
    mock_svc._repo = mock_repo
    mock_svc.get_active_for_admin.return_value = {}
    app.state.ui_theme_service = mock_svc
    resp = client.put(
        "/management/ui-theme/active",
        headers={"Authorization": "Bearer t"},
        json={"presetId": "00000000-0000-0000-0000-000000000099"},
    )
    assert resp.status_code == 404
