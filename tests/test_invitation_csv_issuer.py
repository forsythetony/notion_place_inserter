"""Unit tests for invitation CSV issuer script (issuer bootstrap, create-users flow)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from helper_scripts.invitation_csv_issuer.main import (
    _common_options,
    _ensure_issuer_admin_account,
    _upsert_admin_profile,
)


@pytest.fixture
def mock_supabase_client():
    client = MagicMock()
    # Default: empty user list (issuer does not exist)
    mock_list_resp = MagicMock()
    mock_list_resp.users = []
    client.auth.admin.list_users.return_value = mock_list_resp
    # Default: create_user succeeds
    mock_user = MagicMock()
    mock_user.id = "880e8400-e29b-41d4-a716-446655440001"
    mock_user.email = "admin@example.com"
    mock_create_resp = MagicMock()
    mock_create_resp.user = mock_user
    client.auth.admin.create_user.return_value = mock_create_resp
    # Table upsert chain
    client.table.return_value.upsert.return_value.execute.return_value = None
    return client


@pytest.fixture
def mock_create_client(mock_supabase_client):
    with patch(
        "helper_scripts.invitation_csv_issuer.main.create_client",
        return_value=mock_supabase_client,
    ):
        yield mock_supabase_client


def test_ensure_issuer_admin_account_creates_when_missing(mock_create_client):
    """When issuer does not exist, creates auth user and upserts ADMIN profile."""
    _ensure_issuer_admin_account(
        supabase_url="http://127.0.0.1:54321",
        supabase_secret_key="secret",
        email="admin@example.com",
        password="adminpass123",
    )
    mock_create_client.auth.admin.create_user.assert_called_once()
    call_kw = mock_create_client.auth.admin.create_user.call_args[0][0]
    assert call_kw["email"] == "admin@example.com"
    assert call_kw["password"] == "adminpass123"
    assert call_kw["email_confirm"] is True
    mock_create_client.table.assert_called_with("user_profiles")
    mock_create_client.table.return_value.upsert.assert_called_once()


def test_ensure_issuer_admin_account_idempotent_when_exists(mock_create_client):
    """When issuer already exists, does not create user; only ensures profile."""
    mock_user = MagicMock()
    mock_user.id = "990e8400-e29b-41d4-a716-446655440002"
    mock_user.email = "admin@example.com"
    mock_list_resp = MagicMock()
    mock_list_resp.users = [mock_user]
    mock_create_client.auth.admin.list_users.return_value = mock_list_resp

    _ensure_issuer_admin_account(
        supabase_url="http://127.0.0.1:54321",
        supabase_secret_key="secret",
        email="admin@example.com",
        password="adminpass123",
    )
    mock_create_client.auth.admin.create_user.assert_not_called()
    mock_create_client.table.return_value.upsert.assert_called_once()


def test_ensure_issuer_admin_account_handles_duplicate_on_create(mock_create_client):
    """When create_user raises 'already exists', re-lists and ensures profile."""
    mock_create_client.auth.admin.create_user.side_effect = Exception(
        "User already registered with this email"
    )
    mock_user = MagicMock()
    mock_user.id = "aa0e8400-e29b-41d4-a716-446655440003"
    mock_user.email = "admin@example.com"
    mock_list_empty = MagicMock()
    mock_list_empty.users = []
    mock_list_with_user = MagicMock()
    mock_list_with_user.users = [mock_user]
    mock_create_client.auth.admin.list_users.side_effect = [
        mock_list_empty,
        mock_list_with_user,
    ]

    _ensure_issuer_admin_account(
        supabase_url="http://127.0.0.1:54321",
        supabase_secret_key="secret",
        email="admin@example.com",
        password="adminpass123",
    )
    mock_create_client.auth.admin.create_user.assert_called_once()
    mock_create_client.table.return_value.upsert.assert_called_once()


def test_upsert_admin_profile_calls_table_upsert(mock_supabase_client):
    """_upsert_admin_profile upserts user_profiles with ADMIN."""
    _upsert_admin_profile(mock_supabase_client, "user-uuid-123")
    mock_supabase_client.table.assert_called_with("user_profiles")
    upsert_call = mock_supabase_client.table.return_value.upsert.call_args
    assert upsert_call[0][0]["user_id"] == "user-uuid-123"
    assert upsert_call[0][0]["user_type"] == "ADMIN"
    assert upsert_call[1].get("on_conflict") == "user_id"


def test_common_options_bootstrap_issuer_false_skips_ensure_issuer(mock_create_client):
    """When bootstrap_issuer=False, _ensure_issuer_admin_account is not called."""
    with patch(
        "helper_scripts.invitation_csv_issuer.main.create_client",
        return_value=mock_create_client,
    ):
        with patch(
            "helper_scripts.invitation_csv_issuer.main._get_token",
            return_value="fake-token",
        ):
            with patch(
                "helper_scripts.invitation_csv_issuer.main._ensure_admin_profile",
            ):
                _common_options(
                    csv_path=Path("/tmp/foo.csv"),
                    api_base_url="http://localhost:8000",
                    supabase_url="http://127.0.0.1:54321",
                    supabase_publishable_key="anon",
                    supabase_secret_key="secret",
                    username="admin@example.com",
                    password="adminpass123",
                    timeout_seconds=10.0,
                    output_path=None,
                    bootstrap_issuer=False,
                )
    mock_create_client.auth.admin.list_users.assert_not_called()
    mock_create_client.auth.admin.create_user.assert_not_called()


def test_common_options_bootstrap_issuer_true_calls_ensure_issuer(mock_create_client):
    """When bootstrap_issuer=True, _ensure_issuer_admin_account is called before token."""
    with patch(
        "helper_scripts.invitation_csv_issuer.main.create_client",
        return_value=mock_create_client,
    ):
        with patch(
            "helper_scripts.invitation_csv_issuer.main._get_token",
            return_value="fake-token",
        ):
            with patch(
                "helper_scripts.invitation_csv_issuer.main._ensure_admin_profile",
            ):
                _common_options(
                    csv_path=Path("/tmp/foo.csv"),
                    api_base_url="http://localhost:8000",
                    supabase_url="http://127.0.0.1:54321",
                    supabase_publishable_key="anon",
                    supabase_secret_key="secret",
                    username="admin@example.com",
                    password="adminpass123",
                    timeout_seconds=10.0,
                    output_path=None,
                    bootstrap_issuer=True,
                )
    mock_create_client.auth.admin.list_users.assert_called()
    mock_create_client.auth.admin.create_user.assert_called_once()
