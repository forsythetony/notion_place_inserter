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


def test_get_invitation_by_issued_to_returns_row_when_found(repo, mock_client):
    """get_invitation_by_issued_to returns dict when invitation exists for issued_to."""
    mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "inv-issued",
                "code": "x" * 20,
                "user_type": USER_TYPE_STANDARD,
                "issued_to": "alice@example.com",
                "claimed": False,
            }
        ]
    )
    row = repo.get_invitation_by_issued_to("alice@example.com")
    assert row is not None
    assert row["issued_to"] == "alice@example.com"
    assert row["code"] == "x" * 20
    mock_client.table.assert_called_with("invitation_codes")
    mock_client.table.return_value.select.return_value.eq.assert_called_with(
        "issued_to", "alice@example.com"
    )


def test_get_invitation_by_issued_to_returns_none_when_not_found(repo, mock_client):
    """get_invitation_by_issued_to returns None when no invitation for issued_to."""
    mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    row = repo.get_invitation_by_issued_to("nobody@example.com")
    assert row is None


def test_get_invitation_by_issued_to_returns_none_for_empty_string(repo, mock_client):
    """get_invitation_by_issued_to returns None for empty/whitespace issued_to."""
    row = repo.get_invitation_by_issued_to("")
    assert row is None
    row = repo.get_invitation_by_issued_to("   ")
    assert row is None
    mock_client.table.assert_not_called()


def test_validate_invitation_code_returns_invalid_when_not_found(repo, mock_client):
    """validate_invitation_code returns status invalid when code not found."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    result = repo.validate_invitation_code("f" * 20)
    assert result["status"] == "invalid"


def test_validate_invitation_code_returns_already_claimed_when_claimed(repo, mock_client):
    """validate_invitation_code returns status already_claimed when claimed."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": "inv-1", "code": "g" * 20, "claimed": True, "user_type": USER_TYPE_STANDARD}]
    )
    result = repo.validate_invitation_code("g" * 20)
    assert result["status"] == "already_claimed"


def test_validate_invitation_code_returns_valid_when_claimable(repo, mock_client):
    """validate_invitation_code returns status valid with user_type when claimable."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": "inv-2", "code": "h" * 20, "claimed": False, "user_type": USER_TYPE_BETA_TESTER}]
    )
    result = repo.validate_invitation_code("h" * 20)
    assert result["status"] == "valid"
    assert result["user_type"] == USER_TYPE_BETA_TESTER
    assert result["id"] == "inv-2"


def test_claim_invitation_code_returns_row_when_success(repo, mock_client):
    """claim_invitation_code returns claimed row when update affects a row."""
    mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "inv-3", "code": "i" * 20, "claimed": True, "user_type": USER_TYPE_STANDARD}]
    )
    result = repo.claim_invitation_code("i" * 20, "550e8400-e29b-41d4-a716-446655440000")
    assert result is not None
    assert result["claimed"] is True
    assert result["user_type"] == USER_TYPE_STANDARD
    call_arg = mock_client.table.return_value.update.call_args[0][0]
    assert call_arg["claimed"] is True
    assert "claimed_by_user_id" in call_arg


def test_claim_invitation_code_returns_none_when_already_claimed(repo, mock_client):
    """claim_invitation_code returns None when no row matched (already claimed)."""
    mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )
    result = repo.claim_invitation_code("j" * 20, "550e8400-e29b-41d4-a716-446655440000")
    assert result is None


def test_claim_invitation_code_for_signup_claims_and_upserts_profile(repo, mock_client):
    """claim_invitation_code_for_signup claims code and upserts user profile."""
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    code = "k" * 20
    claimed_row = {
        "id": "inv-999",
        "code": code,
        "claimed": True,
        "user_type": USER_TYPE_BETA_TESTER,
    }
    mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[claimed_row]
    )
    mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock(
        data=[]
    )
    result = repo.claim_invitation_code_for_signup(code, user_id)
    assert result is not None
    assert result["user_type"] == USER_TYPE_BETA_TESTER
    assert result["id"] == "inv-999"
    mock_client.table.return_value.upsert.assert_called_once()
    call_kw = mock_client.table.return_value.upsert.call_args
    payload = call_kw[0][0]
    assert payload["user_id"] == user_id
    assert payload["user_type"] == USER_TYPE_BETA_TESTER
    assert payload["invitation_code_id"] == "inv-999"


def test_claim_invitation_code_for_signup_returns_none_when_claim_fails(repo, mock_client):
    """claim_invitation_code_for_signup returns None when claim returns None."""
    mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )
    result = repo.claim_invitation_code_for_signup(
        "l" * 20, "550e8400-e29b-41d4-a716-446655440000"
    )
    assert result is None
    mock_client.table.return_value.upsert.assert_not_called()


def test_generate_invitation_code_returns_20_char_code_when_no_collision(repo, mock_client):
    """generate_invitation_code returns 20-char code when no collision."""
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    code = repo.generate_invitation_code()
    assert len(code) == 20
    assert all(c in "0123456789abcdef" for c in code)
