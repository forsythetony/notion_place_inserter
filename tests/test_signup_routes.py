"""Unit tests for signup-with-invitation orchestration route."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app

_EULA_ID = "11111111-1111-4111-8111-111111111111"
_SIGNUP_EULA = {"eula_version_id": _EULA_ID, "eula_accepted": True}


@pytest.fixture
def client():
    return TestClient(app)


def _setup_signup_service_mock():
    """Configure app state with mocked signup orchestration service."""
    mock_service = MagicMock()
    app.state.signup_orchestration_service = mock_service
    return mock_service


def test_signup_400_invalid_code(client):
    """POST /auth/signup with invalid code returns 400, no auth user created."""
    mock_svc = _setup_signup_service_mock()
    mock_svc.signup_with_invitation.side_effect = ValueError("Invalid invitation code")

    resp = client.post(
        "/auth/signup",
        json={
            "email": "user@example.com",
            "password": "password123",
            "code": "x" * 20,
            **_SIGNUP_EULA,
        },
    )
    assert resp.status_code == 400
    assert "Invalid invitation code" in resp.json()["detail"]
    mock_svc.signup_with_invitation.assert_called_once_with(
        email="user@example.com",
        password="password123",
        code="x" * 20,
        eula_version_id=_EULA_ID,
        eula_accepted=True,
    )


def test_signup_400_already_claimed(client):
    """POST /auth/signup with already-claimed code returns 400, no auth user created."""
    mock_svc = _setup_signup_service_mock()
    mock_svc.signup_with_invitation.side_effect = ValueError(
        "Invitation code already claimed"
    )

    resp = client.post(
        "/auth/signup",
        json={
            "email": "user@example.com",
            "password": "password123",
            "code": "a" * 20,
            **_SIGNUP_EULA,
        },
    )
    assert resp.status_code == 400
    assert "already claimed" in resp.json()["detail"].lower()


def test_signup_200_success(client):
    """POST /auth/signup with valid code creates user and returns user_id, user_type."""
    mock_svc = _setup_signup_service_mock()
    mock_svc.signup_with_invitation.return_value = {
        "user_id": "880e8400-e29b-41d4-a716-446655440003",
        "user_type": "STANDARD",
    }

    resp = client.post(
        "/auth/signup",
        json={
            "email": "newuser@example.com",
            "password": "securepass123",
            "code": "b" * 20,
            **_SIGNUP_EULA,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "880e8400-e29b-41d4-a716-446655440003"
    assert data["user_type"] == "STANDARD"
    mock_svc.signup_with_invitation.assert_called_once_with(
        email="newuser@example.com",
        password="securepass123",
        code="b" * 20,
        eula_version_id=_EULA_ID,
        eula_accepted=True,
    )


def test_signup_400_validation_short_code(client):
    """POST /auth/signup with code not 20 chars returns 400 from Pydantic."""
    resp = client.post(
        "/auth/signup",
        json={
            "email": "user@example.com",
            "password": "password123",
            "code": "short",
        },
    )
    assert resp.status_code == 422


def test_signup_400_validation_short_password(client):
    """POST /auth/signup with password < 6 chars returns 400 from Pydantic."""
    mock_svc = _setup_signup_service_mock()

    resp = client.post(
        "/auth/signup",
        json={
            "email": "user@example.com",
            "password": "12345",
            "code": "a" * 20,
            **_SIGNUP_EULA,
        },
    )
    assert resp.status_code == 422
    mock_svc.signup_with_invitation.assert_not_called()
