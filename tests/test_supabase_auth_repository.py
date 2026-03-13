"""Unit tests for Supabase auth repository (with mocks)."""

from unittest.mock import MagicMock

import pytest

from app.integrations.supabase_config import SupabaseConfig
from app.services.supabase_auth_repository import (
    SupabaseAuthRepository,
    USER_TYPE_ADMIN,
    USER_TYPE_BETA_TESTER,
    USER_TYPE_STANDARD,
)


@pytest.fixture
def config():
    return SupabaseConfig(
        url="https://test.supabase.co",
        secret_key="test-key",
        queue_name="locations_jobs",
        table_platform_jobs="platform_jobs",
        table_pipeline_runs="pipeline_runs",
        table_pipeline_run_events="pipeline_run_events",
        table_user_profiles="user_profiles",
        table_invitation_codes="invitation_codes",
    )


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def repo(mock_client, config):
    return SupabaseAuthRepository(mock_client, config)


def test_upsert_profile_inserts_into_user_profiles(repo, mock_client):
    """Upsert profile calls user_profiles table with user_id, user_type."""
    repo.upsert_profile("550e8400-e29b-41d4-a716-446655440000", USER_TYPE_ADMIN)
    mock_client.table.assert_called_with("user_profiles")
    mock_client.table.return_value.upsert.assert_called_once()
    call_arg = mock_client.table.return_value.upsert.call_args[0][0]
    assert call_arg["user_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert call_arg["user_type"] == USER_TYPE_ADMIN
    assert "updated_at" in call_arg


def test_upsert_profile_with_invitation_code_id(repo, mock_client):
    """Upsert profile includes invitation_code_id when provided."""
    repo.upsert_profile(
        "550e8400-e29b-41d4-a716-446655440000",
        USER_TYPE_STANDARD,
        invitation_code_id="660e8400-e29b-41d4-a716-446655440001",
    )
    call_arg = mock_client.table.return_value.upsert.call_args[0][0]
    assert call_arg["invitation_code_id"] == "660e8400-e29b-41d4-a716-446655440001"


def test_upsert_profile_rejects_invalid_user_type(repo):
    """Upsert profile raises ValueError for invalid user_type."""
    with pytest.raises(ValueError) as exc_info:
        repo.upsert_profile("550e8400-e29b-41d4-a716-446655440000", "INVALID")
    assert "user_type" in str(exc_info.value).lower()
    assert "INVALID" in str(exc_info.value)


def test_get_profile_returns_profile_when_found(repo, mock_client):
    """get_profile returns dict when profile exists."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"user_id": "550e8400-e29b-41d4-a716-446655440000", "user_type": USER_TYPE_BETA_TESTER}]
    )
    profile = repo.get_profile("550e8400-e29b-41d4-a716-446655440000")
    assert profile is not None
    assert profile["user_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert profile["user_type"] == USER_TYPE_BETA_TESTER
    mock_client.table.assert_called_with("user_profiles")


def test_get_profile_returns_none_when_not_found(repo, mock_client):
    """get_profile returns None when profile does not exist."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    profile = repo.get_profile("550e8400-e29b-41d4-a716-446655440000")
    assert profile is None


def test_create_invitation_code_inserts_into_invitation_codes(repo, mock_client):
    """Create invitation code inserts row with code, user_type, claimed=false."""
    mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "abc-123", "code": "a" * 20, "user_type": USER_TYPE_STANDARD, "claimed": False}]
    )
    result = repo.create_invitation_code("a" * 20, USER_TYPE_STANDARD)
    mock_client.table.assert_called_with("invitation_codes")
    call_arg = mock_client.table.return_value.insert.call_args[0][0]
    assert call_arg["code"] == "a" * 20
    assert call_arg["user_type"] == USER_TYPE_STANDARD
    assert call_arg["claimed"] is False
    assert result["code"] == "a" * 20


def test_create_invitation_code_with_metadata(repo, mock_client):
    """Create invitation code includes issued_to and platform_issued_on when provided."""
    mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "abc-123", "code": "b" * 20}]
    )
    repo.create_invitation_code(
        "b" * 20,
        USER_TYPE_ADMIN,
        issued_to="user@example.com",
        platform_issued_on="beta-signup",
    )
    call_arg = mock_client.table.return_value.insert.call_args[0][0]
    assert call_arg["issued_to"] == "user@example.com"
    assert call_arg["platform_issued_on"] == "beta-signup"


def test_create_invitation_code_rejects_invalid_user_type(repo):
    """Create invitation code raises ValueError for invalid user_type."""
    with pytest.raises(ValueError) as exc_info:
        repo.create_invitation_code("c" * 20, "INVALID")
    assert "user_type" in str(exc_info.value).lower()


def test_create_invitation_code_rejects_wrong_code_length(repo):
    """Create invitation code raises ValueError when code is not 20 chars."""
    with pytest.raises(ValueError) as exc_info:
        repo.create_invitation_code("short", USER_TYPE_ADMIN)
    assert "20" in str(exc_info.value)


def test_get_invitation_code_by_code_returns_row_when_found(repo, mock_client):
    """get_invitation_code_by_code returns dict when code exists."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": "inv-1", "code": "d" * 20, "claimed": False}]
    )
    row = repo.get_invitation_code_by_code("d" * 20)
    assert row is not None
    assert row["code"] == "d" * 20
    mock_client.table.assert_called_with("invitation_codes")


def test_get_invitation_code_by_code_returns_none_when_not_found(repo, mock_client):
    """get_invitation_code_by_code returns None when code does not exist."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    row = repo.get_invitation_code_by_code("e" * 20)
    assert row is None
