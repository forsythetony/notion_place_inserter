"""Unit tests for SignupOrchestrationService."""

from unittest.mock import MagicMock

import pytest

from app.services.signup_orchestration_service import SignupOrchestrationService


@pytest.fixture
def mock_supabase_client():
    return MagicMock()


@pytest.fixture
def mock_auth_repo():
    return MagicMock()


@pytest.fixture
def service(mock_supabase_client, mock_auth_repo):
    return SignupOrchestrationService(mock_supabase_client, mock_auth_repo)


def test_signup_invalid_code_does_not_create_user(service, mock_supabase_client, mock_auth_repo):
    """Invalid code: validate fails, create_user never called."""
    mock_auth_repo.validate_invitation_code.return_value = {"status": "invalid"}

    with pytest.raises(ValueError, match="Invalid invitation code"):
        service.signup_with_invitation(
            email="user@example.com",
            password="password123",
            code="x" * 20,
        )

    mock_auth_repo.validate_invitation_code.assert_called_once_with("x" * 20)
    mock_supabase_client.auth.admin.create_user.assert_not_called()


def test_signup_already_claimed_does_not_create_user(service, mock_supabase_client, mock_auth_repo):
    """Already-claimed code: validate fails, create_user never called."""
    mock_auth_repo.validate_invitation_code.return_value = {"status": "already_claimed"}

    with pytest.raises(ValueError, match="already claimed"):
        service.signup_with_invitation(
            email="user@example.com",
            password="password123",
            code="a" * 20,
        )

    mock_supabase_client.auth.admin.create_user.assert_not_called()


def test_signup_success_creates_user_and_claims(service, mock_supabase_client, mock_auth_repo):
    """Valid code: create user, claim, provision profile."""
    mock_auth_repo.validate_invitation_code.return_value = {
        "status": "valid",
        "user_type": "STANDARD",
        "id": "inv-123",
    }
    mock_user = MagicMock()
    mock_user.id = "880e8400-e29b-41d4-a716-446655440003"
    mock_create_resp = MagicMock()
    mock_create_resp.user = mock_user
    mock_supabase_client.auth.admin.create_user.return_value = mock_create_resp
    mock_auth_repo.claim_invitation_code_for_signup.return_value = {
        "id": "inv-123",
        "user_type": "STANDARD",
        "claimed": True,
    }

    result = service.signup_with_invitation(
        email="newuser@example.com",
        password="securepass123",
        code="b" * 20,
    )

    assert result["user_id"] == "880e8400-e29b-41d4-a716-446655440003"
    assert result["user_type"] == "STANDARD"
    mock_supabase_client.auth.admin.create_user.assert_called_once()
    mock_auth_repo.claim_invitation_code_for_signup.assert_called_once_with(
        "b" * 20,
        "880e8400-e29b-41d4-a716-446655440003",
    )


def test_signup_claim_race_deletes_orphan_user(service, mock_supabase_client, mock_auth_repo):
    """When claim returns None (race), delete the just-created auth user."""
    mock_auth_repo.validate_invitation_code.return_value = {
        "status": "valid",
        "user_type": "STANDARD",
        "id": "inv-123",
    }
    mock_user = MagicMock()
    mock_user.id = "990e8400-e29b-41d4-a716-446655440004"
    mock_create_resp = MagicMock()
    mock_create_resp.user = mock_user
    mock_supabase_client.auth.admin.create_user.return_value = mock_create_resp
    mock_auth_repo.claim_invitation_code_for_signup.return_value = None

    with pytest.raises(ValueError, match="already claimed"):
        service.signup_with_invitation(
            email="race@example.com",
            password="password123",
            code="c" * 20,
        )

    mock_supabase_client.auth.admin.delete_user.assert_called_once_with(
        "990e8400-e29b-41d4-a716-446655440004"
    )
