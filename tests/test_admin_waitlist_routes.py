"""Tests for admin waitlist and beta wave HTTP routes."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.supabase_auth_repository import USER_TYPE_ADMIN, USER_TYPES


@pytest.fixture
def client():
    return TestClient(app)


def _mock_user(id_, email="admin@example.com"):
    u = MagicMock()
    u.id = id_
    u.email = email
    return u


def _mock_user_response(user):
    r = MagicMock()
    r.user = user
    return r


def _admin_with_waitlist():
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user = AsyncMock(
        return_value=_mock_user_response(_mock_user(user_id))
    )
    mock_auth_repo = MagicMock()
    mock_auth_repo.get_profile = AsyncMock(
        return_value={"user_id": user_id, "user_type": USER_TYPE_ADMIN}
    )
    mock_waitlist = MagicMock()
    app.state.supabase_client = mock_supabase
    app.state.supabase_auth_repository = mock_auth_repo
    app.state.beta_waitlist_repository = mock_waitlist
    return user_id, mock_auth_repo, mock_waitlist


def test_list_beta_waves_200(client):
    _admin_with_waitlist()
    app.state.supabase_auth_repository.list_beta_waves = AsyncMock(
        return_value=[
            {
                "id": "11111111-1111-4111-8111-111111111111",
                "key": "WAVE_1",
                "label": "Wave 1",
                "description": None,
                "sort_order": 10,
                "created_at": None,
                "updated_at": None,
            }
        ]
    )
    resp = client.get(
        "/auth/admin/beta-waves",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["key"] == "WAVE_1"
    assert data["items"][0]["sortOrder"] == 10


def test_list_waitlist_submissions_200(client):
    _, _, mock_wl = _admin_with_waitlist()
    mock_wl.list_for_admin = AsyncMock(
        return_value=(
            [
                {
                    "id": "22222222-2222-4222-8222-222222222222",
                    "email": "w@example.com",
                    "email_normalized": "w@example.com",
                    "name": "W",
                    "heard_about": "twitter",
                    "heard_about_other": None,
                    "work_role": "eng",
                    "notion_use_case": "CRM",
                    "status": "PENDING_REVIEW",
                    "submission_count": 1,
                    "first_submitted_at": None,
                    "last_submitted_at": None,
                    "invitation_code_id": None,
                    "invited_at": None,
                    "reviewed_at": None,
                    "admin_notes": None,
                    "beta_wave_id": None,
                    "created_at": None,
                    "updated_at": None,
                    "beta_wave_key": None,
                }
            ],
            False,
        )
    )
    resp = client.get(
        "/auth/admin/waitlist-submissions",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["email"] == "w@example.com"
    assert body["nextCursor"] is None


def test_patch_waitlist_submission_200(client):
    _, mock_auth, mock_wl = _admin_with_waitlist()
    wid = "11111111-1111-4111-8111-111111111111"
    mock_auth.get_beta_wave_by_id = AsyncMock(return_value={"id": wid, "key": "WAVE_1"})
    sid = "22222222-2222-4222-8222-222222222222"
    mock_wl.patch_submission_admin = AsyncMock(
        return_value={
            "id": sid,
            "email": "w@example.com",
            "email_normalized": "w@example.com",
            "name": "W",
            "heard_about": "twitter",
            "heard_about_other": None,
            "work_role": "eng",
            "notion_use_case": "CRM",
            "status": "SHORTLISTED",
            "submission_count": 1,
            "first_submitted_at": None,
            "last_submitted_at": None,
            "invitation_code_id": None,
            "invited_at": None,
            "reviewed_at": None,
            "admin_notes": "ok",
            "beta_wave_id": wid,
            "created_at": None,
            "updated_at": None,
            "beta_wave_key": "WAVE_1",
        }
    )
    resp = client.patch(
        f"/auth/admin/waitlist-submissions/{sid}",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"adminNotes": "ok", "betaWaveId": wid, "status": "SHORTLISTED"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "SHORTLISTED"
    mock_wl.patch_submission_admin.assert_called_once()


def test_issue_from_waitlist_creates_invite(client):
    _, mock_auth, mock_wl = _admin_with_waitlist()
    sid = "22222222-2222-4222-8222-222222222222"
    mock_wl.get_by_id = AsyncMock(
        return_value={
            "id": sid,
            "email": "wait@example.com",
            "email_normalized": "wait@example.com",
            "invitation_code_id": None,
            "beta_wave_id": None,
            "status": "PENDING_REVIEW",
            "admin_notes": None,
            "beta_wave_key": None,
            "name": "N",
            "heard_about": "x",
            "heard_about_other": None,
            "work_role": "r",
            "notion_use_case": "u",
            "submission_count": 1,
            "first_submitted_at": None,
            "last_submitted_at": None,
            "invited_at": None,
            "reviewed_at": None,
            "created_at": None,
            "updated_at": None,
        }
    )
    mock_auth.get_invitation_by_issued_to = AsyncMock(return_value=None)
    mock_auth.generate_invitation_code = AsyncMock(return_value="c" * 20)
    inv_id = "33333333-3333-4333-8333-333333333333"
    mock_auth.create_invitation_code = AsyncMock(
        return_value={
            "id": inv_id,
            "code": "c" * 20,
            "user_type": USER_TYPES[2],
            "claimed": False,
            "issued_to": "wait@example.com",
        }
    )
    mock_wl.link_invitation_to_submission = AsyncMock(
        return_value={
            "id": sid,
            "email": "wait@example.com",
            "email_normalized": "wait@example.com",
            "invitation_code_id": inv_id,
            "invited_at": "2026-01-01T00:00:00+00:00",
            "status": "INVITED",
            "beta_wave_id": None,
            "beta_wave_key": None,
            "name": "N",
            "heard_about": "x",
            "heard_about_other": None,
            "work_role": "r",
            "notion_use_case": "u",
            "submission_count": 1,
            "first_submitted_at": None,
            "last_submitted_at": None,
            "reviewed_at": None,
            "admin_notes": None,
            "created_at": None,
            "updated_at": None,
        }
    )
    resp = client.post(
        f"/auth/admin/waitlist-submissions/{sid}/issue-invitation",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"userType": "BETA_TESTER", "platformIssuedOn": "waitlist-ui"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["invitation"]["code"] == "c" * 20
    assert payload["waitlist"]["invitationCodeId"] == inv_id
    mock_auth.create_invitation_code.assert_called_once()
    mock_wl.link_invitation_to_submission.assert_called_once()


def test_create_beta_wave_201(client):
    _, mock_auth, _ = _admin_with_waitlist()
    mock_auth.get_beta_wave_by_key = AsyncMock(return_value=None)
    mock_auth.compute_next_beta_wave_sort_order = AsyncMock(return_value=40)
    wid = "33333333-3333-4333-8333-333333333333"
    mock_auth.create_beta_wave = AsyncMock(
        return_value={
            "id": wid,
            "key": "WAVE_4",
            "label": "Wave 4",
            "description": "d",
            "sort_order": 40,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    )
    resp = client.post(
        "/auth/admin/beta-waves",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"key": "WAVE_4", "label": "Wave 4", "description": "d"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["key"] == "WAVE_4"
    assert data["label"] == "Wave 4"
    assert data["sortOrder"] == 40
    mock_auth.create_beta_wave.assert_called_once()


def test_create_beta_wave_409_duplicate_key(client):
    _, mock_auth, _ = _admin_with_waitlist()
    mock_auth.get_beta_wave_by_key = AsyncMock(
        return_value={"id": "x", "key": "WAVE_1"}
    )
    resp = client.post(
        "/auth/admin/beta-waves",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"key": "WAVE_1", "label": "Dup"},
    )
    assert resp.status_code == 409


def test_patch_beta_wave_200(client):
    _, mock_auth, _ = _admin_with_waitlist()
    wid = "33333333-3333-4333-8333-333333333333"
    mock_auth.update_beta_wave = AsyncMock(
        return_value={
            "id": wid,
            "key": "WAVE_1",
            "label": "Updated",
            "description": None,
            "sort_order": 15,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
        }
    )
    resp = client.patch(
        f"/auth/admin/beta-waves/{wid}",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"label": "Updated", "description": None, "sortOrder": 15},
    )
    assert resp.status_code == 200
    assert resp.json()["label"] == "Updated"
    assert resp.json()["sortOrder"] == 15


def test_patch_beta_wave_404(client):
    _, mock_auth, _ = _admin_with_waitlist()
    wid = "33333333-3333-4333-8333-333333333333"
    mock_auth.update_beta_wave = AsyncMock(return_value=None)
    resp = client.patch(
        f"/auth/admin/beta-waves/{wid}",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"label": "X", "description": None, "sortOrder": 1},
    )
    assert resp.status_code == 404


def test_delete_beta_wave_204(client):
    _, mock_auth, _ = _admin_with_waitlist()
    wid = "33333333-3333-4333-8333-333333333333"
    mock_auth.delete_beta_wave_if_unused = AsyncMock(return_value="deleted")
    resp = client.delete(
        f"/auth/admin/beta-waves/{wid}",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 204


def test_delete_beta_wave_404(client):
    _, mock_auth, _ = _admin_with_waitlist()
    wid = "33333333-3333-4333-8333-333333333333"
    mock_auth.delete_beta_wave_if_unused = AsyncMock(return_value="not_found")
    resp = client.delete(
        f"/auth/admin/beta-waves/{wid}",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 404


def test_delete_beta_wave_409_in_use(client):
    _, mock_auth, _ = _admin_with_waitlist()
    wid = "33333333-3333-4333-8333-333333333333"
    mock_auth.delete_beta_wave_if_unused = AsyncMock(return_value="in_use")
    resp = client.delete(
        f"/auth/admin/beta-waves/{wid}",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 409
    assert "waitlist" in resp.json()["detail"].lower()
