"""Tests for POST /public/waitlist."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.beta_waitlist_service import BetaWaitlistService
from app.services.waitlist_rate_limiter import InMemoryWaitlistRateLimiter


@pytest.fixture
def client():
    return TestClient(app)


def _valid_body():
    return {
        "email": "user@example.com",
        "name": "Jane",
        "heardAbout": "linkedin",
        "heardAboutOther": None,
        "workRole": "Engineer",
        "notionUseCase": "Automate CRM notes into Notion.",
        "betaFitAccepted": True,
        "captchaToken": "",
        "companyWebsite": "",
    }


def _setup_waitlist_mocks():
    mock_svc = MagicMock()
    app.state.beta_waitlist_service = mock_svc
    app.state.waitlist_rate_limiter = InMemoryWaitlistRateLimiter(
        max_requests=100, window_seconds=3600
    )
    return mock_svc


@patch.dict("os.environ", {"TURNSTILE_ENABLED": "0"}, clear=False)
def test_waitlist_202_success_turnstile_off(client):
    """TURNSTILE_ENABLED off — no Cloudflare verification; captcha token may be empty."""
    mock_svc = _setup_waitlist_mocks()
    resp = client.post("/public/waitlist", json=_valid_body())
    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted"}
    mock_svc.persist_submission.assert_called_once()
    call_kw = mock_svc.persist_submission.call_args.kwargs
    assert call_kw["turnstile_verified"] is False


@patch.dict(
    "os.environ",
    {"TURNSTILE_ENABLED": "1", "TURNSTILE_SECRET_KEY": "ts-secret"},
    clear=False,
)
@patch("app.routes.public_waitlist.verify_turnstile_token", return_value=True)
def test_waitlist_202_success_turnstile_on(mock_verify, client):
    mock_svc = _setup_waitlist_mocks()
    body = _valid_body()
    body["captchaToken"] = "test-token"
    resp = client.post("/public/waitlist", json=body)
    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted"}
    mock_svc.persist_submission.assert_called_once()
    assert mock_svc.persist_submission.call_args.kwargs["turnstile_verified"] is True
    mock_verify.assert_called_once()


@patch.dict("os.environ", {"TURNSTILE_ENABLED": "0"}, clear=False)
def test_waitlist_honeypot_202_no_persist(client):
    mock_svc = _setup_waitlist_mocks()
    body = _valid_body()
    body["companyWebsite"] = "http://spam.com"
    resp = client.post("/public/waitlist", json=body)
    assert resp.status_code == 202
    mock_svc.persist_submission.assert_not_called()


@patch.dict(
    "os.environ",
    {"TURNSTILE_ENABLED": "1", "TURNSTILE_SECRET_KEY": "ts-secret"},
    clear=False,
)
@patch("app.routes.public_waitlist.verify_turnstile_token", return_value=False)
def test_waitlist_400_bad_captcha(mock_verify, client):
    _setup_waitlist_mocks()
    body = _valid_body()
    body["captchaToken"] = "tok"
    resp = client.post("/public/waitlist", json=body)
    assert resp.status_code == 400
    assert "captcha" in resp.json()["detail"].lower()


@patch.dict("os.environ", {"TURNSTILE_ENABLED": "0"}, clear=False)
def test_waitlist_400_other_without_detail(client):
    mock_repo = MagicMock()
    mock_repo.get_by_email_normalized.return_value = None
    app.state.beta_waitlist_service = BetaWaitlistService(
        mock_repo, ip_hash_salt="test-salt"
    )
    app.state.waitlist_rate_limiter = InMemoryWaitlistRateLimiter(
        max_requests=100, window_seconds=3600
    )
    body = _valid_body()
    body["heardAbout"] = "other"
    body["heardAboutOther"] = None
    resp = client.post("/public/waitlist", json=body)
    assert resp.status_code == 400
    mock_repo.insert_submission.assert_not_called()


@patch.dict("os.environ", {"TURNSTILE_ENABLED": "0"}, clear=False)
def test_waitlist_429_rate_limited(client):
    mock_svc = _setup_waitlist_mocks()
    app.state.waitlist_rate_limiter = InMemoryWaitlistRateLimiter(
        max_requests=2, window_seconds=3600
    )
    for _ in range(2):
        r = client.post("/public/waitlist", json=_valid_body())
        assert r.status_code == 202
    r3 = client.post("/public/waitlist", json=_valid_body())
    assert r3.status_code == 429
    assert mock_svc.persist_submission.call_count == 2


@patch.dict(
    "os.environ",
    {"TURNSTILE_ENABLED": "1", "TURNSTILE_SECRET_KEY": ""},
    clear=False,
)
def test_waitlist_500_missing_turnstile_secret_when_enabled(client):
    _setup_waitlist_mocks()
    body = _valid_body()
    body["captchaToken"] = "x"
    resp = client.post("/public/waitlist", json=body)
    assert resp.status_code == 500


@patch.dict(
    "os.environ",
    {"TURNSTILE_ENABLED": "1", "TURNSTILE_SECRET_KEY": "ts-secret"},
    clear=False,
)
def test_waitlist_400_missing_token_when_turnstile_enabled(client):
    _setup_waitlist_mocks()
    resp = client.post("/public/waitlist", json=_valid_body())
    assert resp.status_code == 400
    assert "captcha" in resp.json()["detail"].lower()
