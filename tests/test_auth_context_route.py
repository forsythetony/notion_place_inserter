"""Unit tests for GET /auth/context (dashboard bootstrap) route."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.supabase_auth_repository import USER_TYPE_ADMIN, USER_TYPE_STANDARD


@pytest.fixture
def client():
    return TestClient(app)


def _mock_user(id_: str, email: str | None = "user@example.com"):
    """Build mock Supabase user for get_user response."""
    u = MagicMock()
    u.id = id_
    u.email = email
    return u


def _mock_user_response(user):
    """Build mock UserResponse with .user attribute."""
    r = MagicMock()
    r.user = user
    return r


def test_auth_context_401_without_auth(client):
    """GET /auth/context without Authorization returns 401."""
    resp = client.get("/auth/context")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


def test_auth_context_401_malformed_bearer(client):
    """GET /auth/context with non-Bearer Authorization returns 401."""
    resp = client.get(
        "/auth/context",
        headers={"Authorization": "Basic foo:bar"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


def test_auth_context_401_bearer_no_token(client):
    """GET /auth/context with 'Bearer ' but no token returns 401."""
    resp = client.get(
        "/auth/context",
        headers={"Authorization": "Bearer "},
    )
    assert resp.status_code == 401


def test_auth_context_401_invalid_token(client):
    """GET /auth/context with invalid/expired token returns 401."""
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user = AsyncMock(side_effect=Exception("invalid token"))
    mock_auth_repo = MagicMock()

    app.state.supabase_client = mock_supabase
    app.state.supabase_auth_repository = mock_auth_repo

    resp = client.get(
        "/auth/context",
        headers={"Authorization": "Bearer invalid-jwt-token"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"
    mock_auth_repo.get_profile.assert_not_called()


def test_auth_context_403_profile_not_found(client):
    """GET /auth/context with valid token but no profile returns 403."""
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user = AsyncMock(
        return_value=_mock_user_response(_mock_user(user_id))
    )
    mock_auth_repo = MagicMock()
    mock_auth_repo.get_profile = AsyncMock(return_value=None)

    app.state.supabase_client = mock_supabase
    app.state.supabase_auth_repository = mock_auth_repo

    resp = client.get(
        "/auth/context",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 403
    assert "Profile" in resp.json()["detail"]
    mock_auth_repo.get_profile.assert_called_once_with(user_id)


def test_auth_context_403_profile_missing_user_type(client):
    """GET /auth/context with profile lacking user_type returns 403."""
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user = AsyncMock(
        return_value=_mock_user_response(_mock_user(user_id))
    )
    mock_auth_repo = MagicMock()
    mock_auth_repo.get_profile = AsyncMock(
        return_value={
            "user_id": user_id,
            # no user_type
        }
    )

    app.state.supabase_client = mock_supabase
    app.state.supabase_auth_repository = mock_auth_repo

    resp = client.get(
        "/auth/context",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 403
    assert "incomplete" in resp.json()["detail"].lower()


def test_auth_context_200_valid_token_and_profile(client):
    """GET /auth/context with valid token and profile returns 200 with user_type."""
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    email = "admin@example.com"
    user_type = USER_TYPE_ADMIN

    mock_supabase = MagicMock()
    mock_supabase.auth.get_user = AsyncMock(
        return_value=_mock_user_response(_mock_user(user_id, email))
    )
    mock_auth_repo = MagicMock()
    mock_auth_repo.get_profile = AsyncMock(
        return_value={
            "user_id": user_id,
            "user_type": user_type,
        }
    )

    app.state.supabase_client = mock_supabase
    app.state.supabase_auth_repository = mock_auth_repo

    resp = client.get(
        "/auth/context",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == user_id
    assert data["email"] == email
    assert data["user_type"] == user_type
    mock_auth_repo.get_profile.assert_called_once_with(user_id)


def test_auth_context_200_email_null(client):
    """GET /auth/context returns email null when user has no email."""
    user_id = "660e8400-e29b-41d4-a716-446655440001"
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user = AsyncMock(
        return_value=_mock_user_response(_mock_user(user_id, email=None))
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

    resp = client.get(
        "/auth/context",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] is None
    assert resp.json()["user_type"] == USER_TYPE_STANDARD
