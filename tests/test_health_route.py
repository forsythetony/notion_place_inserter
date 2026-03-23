"""Health check for Render / load balancers."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_200_without_auth():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
