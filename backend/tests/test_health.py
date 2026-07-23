"""Tests for GET /health.

The endpoint is trivial, but it is load-bearing: an external uptime monitor and
every post-deploy smoke test gate on it. These tests pin its contract.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_status_ok():
    """The body is the contract the smoke tests and uptime monitor read."""
    response = client.get("/health")
    assert response.json() == {"status": "ok"}


def test_health_declares_json_content_type():
    response = client.get("/health")
    assert response.headers["content-type"] == "application/json"


def test_health_rejects_post():
    """Only GET is defined; anything else must not silently succeed."""
    response = client.post("/health")
    assert response.status_code == 405
