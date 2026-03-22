"""Unit tests for invitation issuance and claim routes."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from loguru import logger

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


def _setup_admin_auth():
    """Configure app state for admin user auth."""
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.return_value = _mock_user_response(
        _mock_user(user_id, "admin@example.com")
    )
    mock_auth_repo = MagicMock()
    mock_auth_repo.get_profile.return_value = {
        "user_id": user_id,
        "user_type": USER_TYPE_ADMIN,
    }
    app.state.supabase_client = mock_supabase
    app.state.supabase_auth_repository = mock_auth_repo
    return user_id, mock_auth_repo


def _setup_standard_auth():
    """Configure app state for non-admin (STANDARD) user auth."""
    user_id = "660e8400-e29b-41d4-a716-446655440001"
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
    return user_id, mock_auth_repo


def _setup_standard_auth_without_profile():
    """Configure app state for authenticated user with no profile yet."""
    user_id = "760e8400-e29b-41d4-a716-446655440002"
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.return_value = _mock_user_response(
        _mock_user(user_id, "new-user@example.com")
    )
    mock_auth_repo = MagicMock()
    mock_auth_repo.get_profile.return_value = None
    app.state.supabase_client = mock_supabase
    app.state.supabase_auth_repository = mock_auth_repo
    return user_id, mock_auth_repo


def test_issue_invitation_401_without_auth(client):
    """POST /auth/invitations without Authorization returns 401."""
    resp = client.post(
        "/auth/invitations",
        json={"userType": "STANDARD", "issuedTo": "foo", "platformIssuedOn": "web"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


def test_issue_invitation_403_non_admin(client):
    """POST /auth/invitations as non-admin returns 403."""
    _setup_standard_auth()
    resp = client.post(
        "/auth/invitations",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"userType": "STANDARD", "issuedTo": "foo", "platformIssuedOn": "web"},
    )
    assert resp.status_code == 403
    assert "Admin" in resp.json()["detail"]


def test_issue_invitation_200_admin_success(client):
    """POST /auth/invitations as admin creates code and returns persisted metadata."""
    user_id, mock_auth_repo = _setup_admin_auth()
    code = "a" * 20
    mock_auth_repo.get_invitation_by_issued_to.return_value = None  # no existing
    mock_auth_repo.generate_invitation_code.return_value = code
    mock_auth_repo.create_invitation_code.return_value = {
        "id": "inv-123",
        "code": code,
        "user_type": "STANDARD",
        "issued_to": "user@example.com",
        "platform_issued_on": "beta-signup",
        "claimed": False,
    }
    resp = client.post(
        "/auth/invitations",
        headers={"Authorization": "Bearer valid-jwt"},
        json={
            "userType": "STANDARD",
            "issuedTo": "user@example.com",
            "platformIssuedOn": "beta-signup",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == code
    assert data["user_type"] == "STANDARD"
    assert data["issued_to"] == "user@example.com"
    assert data["platform_issued_on"] == "beta-signup"
    assert data["claimed"] is False
    assert data.get("cohortId") is None
    mock_auth_repo.create_invitation_code.assert_called_once_with(
        code=code,
        user_type="STANDARD",
        issued_to="user@example.com",
        platform_issued_on="beta-signup",
        cohort_id=None,
    )


def test_issue_invitation_200_returns_existing_when_issued_to_duplicate(client):
    """POST /auth/invitations with duplicate issuedTo returns existing code (idempotent)."""
    _setup_admin_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    existing_row = {
        "id": "inv-existing",
        "code": "existing" + "x" * 12,
        "user_type": "STANDARD",
        "issued_to": "user@example.com",
        "platform_issued_on": "beta-signup",
        "claimed": False,
    }
    mock_auth_repo.get_invitation_by_issued_to.return_value = existing_row

    resp = client.post(
        "/auth/invitations",
        headers={"Authorization": "Bearer valid-jwt"},
        json={
            "userType": "STANDARD",
            "issuedTo": "user@example.com",
            "platformIssuedOn": "beta-signup",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == existing_row["code"]
    assert data["id"] == "inv-existing"
    assert data["issued_to"] == "user@example.com"
    mock_auth_repo.get_invitation_by_issued_to.assert_called_once_with("user@example.com")
    mock_auth_repo.create_invitation_code.assert_not_called()
    mock_auth_repo.generate_invitation_code.assert_not_called()


def test_issue_invitation_400_invalid_user_type(client):
    """POST /auth/invitations with invalid userType returns 400."""
    _setup_admin_auth()
    resp = client.post(
        "/auth/invitations",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"userType": "INVALID", "issuedTo": "foo", "platformIssuedOn": "web"},
    )
    assert resp.status_code == 400
    assert "userType" in resp.json()["detail"]


def test_validate_invitation_401_without_auth(client):
    """POST /auth/invitations/validate without Authorization returns 401."""
    resp = client.post(
        "/auth/invitations/validate",
        json={"code": "a" * 20},
    )
    assert resp.status_code == 401


def test_validate_invitation_200_invalid(client):
    """POST /auth/invitations/validate returns status invalid for bad code."""
    _setup_standard_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.validate_invitation_code.return_value = {"status": "invalid"}
    resp = client.post(
        "/auth/invitations/validate",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": "x" * 20},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "invalid"


def test_validate_invitation_200_already_claimed(client):
    """POST /auth/invitations/validate returns status already_claimed when claimed."""
    _setup_standard_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.validate_invitation_code.return_value = {
        "status": "already_claimed",
    }
    resp = client.post(
        "/auth/invitations/validate",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": "a" * 20},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "already_claimed"


def test_validate_invitation_200_valid(client):
    """POST /auth/invitations/validate returns status valid with user_type when claimable."""
    _setup_standard_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.validate_invitation_code.return_value = {
        "status": "valid",
        "user_type": "BETA_TESTER",
        "id": "inv-456",
    }
    resp = client.post(
        "/auth/invitations/validate",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": "a" * 20},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "valid"
    assert data["user_type"] == "BETA_TESTER"
    assert data["id"] == "inv-456"


def test_validate_invitation_200_invalid_for_short_code(client):
    """POST /auth/invitations/validate returns invalid for non-20-char code."""
    _setup_standard_auth()
    resp = client.post(
        "/auth/invitations/validate",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": "short"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "invalid"


def test_claim_invitation_401_without_auth(client):
    """POST /auth/invitations/claim without Authorization returns 401."""
    resp = client.post(
        "/auth/invitations/claim",
        json={"code": "a" * 20},
    )
    assert resp.status_code == 401


def test_claim_invitation_400_invalid_code(client):
    """POST /auth/invitations/claim with invalid code returns 400."""
    _setup_standard_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.validate_invitation_code.return_value = {"status": "invalid"}
    resp = client.post(
        "/auth/invitations/claim",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": "a" * 20},
    )
    assert resp.status_code == 400
    assert "Invalid" in resp.json()["detail"]


def test_claim_invitation_400_already_claimed(client):
    """POST /auth/invitations/claim with already-claimed code returns 400."""
    _setup_standard_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.validate_invitation_code.return_value = {
        "status": "already_claimed",
    }
    resp = client.post(
        "/auth/invitations/claim",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": "a" * 20},
    )
    assert resp.status_code == 400
    assert "already claimed" in resp.json()["detail"].lower()


def test_claim_invitation_200_success(client):
    """POST /auth/invitations/claim succeeds once and returns user_type."""
    user_id, mock_auth_repo = _setup_standard_auth()
    code = "a" * 20
    mock_auth_repo.validate_invitation_code.return_value = {
        "status": "valid",
        "user_type": "BETA_TESTER",
        "id": "inv-789",
    }
    mock_auth_repo.claim_invitation_code.return_value = {
        "id": "inv-789",
        "user_type": "BETA_TESTER",
        "claimed": True,
    }
    resp = client.post(
        "/auth/invitations/claim",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": code},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_type"] == "BETA_TESTER"
    assert data["invitation_code_id"] == "inv-789"
    mock_auth_repo.claim_invitation_code.assert_called_once_with(code, user_id)


def test_claim_invitation_400_race_second_attempt(client):
    """POST /auth/invitations/claim returns 400 when claim returns None (race)."""
    _setup_standard_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.validate_invitation_code.return_value = {
        "status": "valid",
        "user_type": "BETA_TESTER",
        "id": "inv-789",
    }
    mock_auth_repo.claim_invitation_code.return_value = None
    resp = client.post(
        "/auth/invitations/claim",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": "a" * 20},
    )
    assert resp.status_code == 400
    assert "already claimed" in resp.json()["detail"].lower()


# --- claim-for-signup ---


def test_claim_for_signup_401_without_auth(client):
    """POST /auth/invitations/claim-for-signup without Authorization returns 401."""
    resp = client.post(
        "/auth/invitations/claim-for-signup",
        json={"code": "a" * 20},
    )
    assert resp.status_code == 401


def test_claim_for_signup_400_invalid_code(client):
    """POST /auth/invitations/claim-for-signup with invalid code returns 400."""
    _setup_standard_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.validate_invitation_code.return_value = {"status": "invalid"}
    resp = client.post(
        "/auth/invitations/claim-for-signup",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": "a" * 20},
    )
    assert resp.status_code == 400
    assert "Invalid" in resp.json()["detail"]


def test_claim_for_signup_400_already_claimed(client):
    """POST /auth/invitations/claim-for-signup with already-claimed code returns 400."""
    _setup_standard_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.validate_invitation_code.return_value = {
        "status": "already_claimed",
    }
    resp = client.post(
        "/auth/invitations/claim-for-signup",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": "a" * 20},
    )
    assert resp.status_code == 400
    assert "already claimed" in resp.json()["detail"].lower()


def test_claim_for_signup_200_success_provisions_profile(client):
    """POST /auth/invitations/claim-for-signup succeeds and provisions user profile."""
    user_id, mock_auth_repo = _setup_standard_auth()
    code = "a" * 20
    mock_auth_repo.validate_invitation_code.return_value = {
        "status": "valid",
        "user_type": "BETA_TESTER",
        "id": "inv-789",
    }
    mock_auth_repo.claim_invitation_code_for_signup.return_value = {
        "id": "inv-789",
        "user_type": "BETA_TESTER",
        "claimed": True,
    }
    resp = client.post(
        "/auth/invitations/claim-for-signup",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": code},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_type"] == "BETA_TESTER"
    assert data["invitation_code_id"] == "inv-789"
    mock_auth_repo.claim_invitation_code_for_signup.assert_called_once_with(
        code, user_id
    )


def test_claim_for_signup_200_success_without_existing_profile(client):
    """POST /auth/invitations/claim-for-signup works even when profile is missing."""
    user_id, mock_auth_repo = _setup_standard_auth_without_profile()
    code = "b" * 20
    mock_auth_repo.validate_invitation_code.return_value = {
        "status": "valid",
        "user_type": "STANDARD",
        "id": "inv-990",
    }
    mock_auth_repo.claim_invitation_code_for_signup.return_value = {
        "id": "inv-990",
        "user_type": "STANDARD",
        "claimed": True,
    }
    resp = client.post(
        "/auth/invitations/claim-for-signup",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": code},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_type"] == "STANDARD"
    assert data["invitation_code_id"] == "inv-990"
    mock_auth_repo.claim_invitation_code_for_signup.assert_called_once_with(
        code, user_id
    )


def test_claim_for_signup_400_race_returns_already_claimed(client):
    """POST /auth/invitations/claim-for-signup returns 400 when claim returns None."""
    _setup_standard_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.validate_invitation_code.return_value = {
        "status": "valid",
        "user_type": "BETA_TESTER",
        "id": "inv-789",
    }
    mock_auth_repo.claim_invitation_code_for_signup.return_value = None
    resp = client.post(
        "/auth/invitations/claim-for-signup",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": "a" * 20},
    )
    assert resp.status_code == 400
    assert "already claimed" in resp.json()["detail"].lower()


def test_claim_invitation_200_admin_user_type(client):
    """POST /auth/invitations/claim succeeds with ADMIN user_type propagation."""
    user_id, mock_auth_repo = _setup_standard_auth()
    code = "a" * 20
    mock_auth_repo.validate_invitation_code.return_value = {
        "status": "valid",
        "user_type": USER_TYPE_ADMIN,
        "id": "inv-admin",
    }
    mock_auth_repo.claim_invitation_code.return_value = {
        "id": "inv-admin",
        "user_type": USER_TYPE_ADMIN,
        "claimed": True,
    }
    resp = client.post(
        "/auth/invitations/claim",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": code},
    )
    assert resp.status_code == 200
    assert resp.json()["user_type"] == USER_TYPE_ADMIN


# --- logging assertions (p2_pr07) ---


@pytest.fixture
def captured_logs():
    """Capture loguru output for invite route logging assertions."""
    output = []

    def sink(message):
        record = message.record
        output.append({"message": record["message"]})

    handler_id = logger.add(sink, level="DEBUG", format="{message}")
    yield output
    logger.remove(handler_id)


def test_issue_invitation_logs_invalid_user_type(client, captured_logs):
    """POST /auth/invitations with invalid userType logs invite_issue_rejected."""
    _setup_admin_auth()
    client.post(
        "/auth/invitations",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"userType": "INVALID", "issuedTo": "foo", "platformIssuedOn": "web"},
    )
    assert any("invite_issue_rejected" in e["message"] for e in captured_logs)
    assert any("invalid_user_type" in e["message"] for e in captured_logs)


def test_claim_invitation_logs_invalid_code(client, captured_logs):
    """POST /auth/invitations/claim with invalid code logs invite_claim_rejected."""
    _setup_standard_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.validate_invitation_code.return_value = {"status": "invalid"}
    client.post(
        "/auth/invitations/claim",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": "a" * 20},
    )
    assert any("invite_claim_rejected" in e["message"] for e in captured_logs)
    assert any("invalid_code" in e["message"] for e in captured_logs)


def test_claim_invitation_logs_claim_race(client, captured_logs):
    """POST /auth/invitations/claim with race (None) logs invite_claim_rejected."""
    _setup_standard_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.validate_invitation_code.return_value = {
        "status": "valid",
        "user_type": "BETA_TESTER",
        "id": "inv-789",
    }
    mock_auth_repo.claim_invitation_code.return_value = None
    client.post(
        "/auth/invitations/claim",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": "a" * 20},
    )
    assert any("invite_claim_rejected" in e["message"] for e in captured_logs)
    assert any("claim_race" in e["message"] for e in captured_logs)


def test_claim_for_signup_logs_invalid_code(client, captured_logs):
    """POST /auth/invitations/claim-for-signup with invalid code logs rejection."""
    _setup_standard_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.validate_invitation_code.return_value = {"status": "invalid"}
    client.post(
        "/auth/invitations/claim-for-signup",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"code": "a" * 20},
    )
    assert any("invite_claim_for_signup_rejected" in e["message"] for e in captured_logs)


def test_list_invitations_200_admin(client):
    """GET /auth/invitations returns items for admin."""
    _setup_admin_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.list_invitation_codes_for_admin.return_value = [
        {
            "id": "i1",
            "code": "a" * 20,
            "user_type": "STANDARD",
            "cohort_id": None,
            "cohort_key": None,
            "issued_to": "x@y.com",
            "platform_issued_on": "web",
            "claimed": False,
            "date_issued": "2026-01-01T00:00:00+00:00",
            "date_claimed": None,
            "claimed_at": None,
            "claimed_by_user_id": None,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    ]
    resp = client.get(
        "/auth/invitations",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["userType"] == "STANDARD"
    assert data["items"][0]["code"] == "a" * 20


def test_list_invitations_403_non_admin(client):
    """GET /auth/invitations as non-admin returns 403."""
    _setup_standard_auth()
    resp = client.get(
        "/auth/invitations",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 403


def test_delete_invitation_204_unclaimed(client):
    """DELETE unclaimed invitation returns 204."""
    _setup_admin_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.delete_unclaimed_invitation_by_id.return_value = "deleted"
    resp = client.delete(
        "/auth/invitations/550e8400-e29b-41d4-a716-446655440000",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 204


def test_delete_invitation_404_not_found(client):
    _setup_admin_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.delete_unclaimed_invitation_by_id.return_value = "not_found"
    resp = client.delete(
        "/auth/invitations/550e8400-e29b-41d4-a716-446655440000",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 404


def test_delete_invitation_409_claimed(client):
    _setup_admin_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.delete_unclaimed_invitation_by_id.return_value = "claimed"
    resp = client.delete(
        "/auth/invitations/550e8400-e29b-41d4-a716-446655440000",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 409


def test_issue_invitation_400_invalid_cohort_id(client):
    """POST /auth/invitations with unknown cohortId returns 400."""
    _setup_admin_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.get_cohort_by_id.return_value = None
    resp = client.post(
        "/auth/invitations",
        headers={"Authorization": "Bearer valid-jwt"},
        json={
            "userType": "STANDARD",
            "cohortId": "a0000000-0000-4000-8000-000000000099",
        },
    )
    assert resp.status_code == 400
    mock_auth_repo.create_invitation_code.assert_not_called()


def test_issue_invitation_passes_cohort_id_to_create(client):
    _setup_admin_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.get_invitation_by_issued_to.return_value = None
    mock_auth_repo.generate_invitation_code.return_value = "b" * 20
    cid = "a0000000-0000-4000-8000-000000000001"
    mock_auth_repo.get_cohort_by_id.return_value = {"id": cid, "key": "STUDENT_A"}
    mock_auth_repo.create_invitation_code.return_value = {
        "id": "inv-c",
        "code": "b" * 20,
        "user_type": "BETA_TESTER",
        "cohort_id": cid,
        "claimed": False,
    }
    resp = client.post(
        "/auth/invitations",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"userType": "BETA_TESTER", "cohortId": cid},
    )
    assert resp.status_code == 200
    mock_auth_repo.create_invitation_code.assert_called_once()
    kw = mock_auth_repo.create_invitation_code.call_args.kwargs
    assert kw["cohort_id"] == cid


def test_list_user_profiles_admin_200(client):
    _setup_admin_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.list_user_profiles_for_admin.return_value = [
        {
            "user_id": "550e8400-e29b-41d4-a716-446655440000",
            "user_type": "STANDARD",
            "email": "user@example.com",
            "invitation_code_id": None,
            "cohort_id": None,
            "cohort_key": None,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    ]
    resp = client.get(
        "/auth/admin/user-profiles",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    assert resp.json()["items"][0]["userId"] == "550e8400-e29b-41d4-a716-446655440000"
    assert resp.json()["items"][0]["email"] == "user@example.com"


def test_list_user_profiles_admin_403(client):
    _setup_standard_auth()
    resp = client.get(
        "/auth/admin/user-profiles",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 403


def test_list_cohorts_admin_200(client):
    _setup_admin_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.list_cohorts.return_value = [
        {
            "id": "c1",
            "key": "A",
            "description": "d",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    ]
    resp = client.get(
        "/auth/admin/cohorts",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    assert resp.json()["items"][0]["key"] == "A"


def test_create_cohort_409_duplicate_key(client):
    _setup_admin_auth()
    mock_auth_repo = app.state.supabase_auth_repository
    mock_auth_repo.get_cohort_by_key.return_value = {"id": "x"}
    resp = client.post(
        "/auth/admin/cohorts",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"key": "DUPE", "description": "x"},
    )
    assert resp.status_code == 409
