"""Tests for CORS on /chat.

The web frontend and this API are different origins in production
(ljubenvassilev.com vs api.ljubenvassilev.com — decision 48's domain split).
Without CORSMiddleware, every browser fetch() fails with a generic "Failed to
fetch" the browser never explains further, even though curl (which does not
enforce CORS) works fine — these tests pin that a browser preflight actually
succeeds, that the real response carries the header too, and that an origin
not on the allowlist gets neither.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import main, rag
from app.config import ALLOWED_ORIGINS
from tests.conftest import FakeMessage, FakeTextBlock

client = TestClient(main.app)

ALLOWED = ALLOWED_ORIGINS[0]


def test_allowed_origin_gets_preflight_approval():
    response = client.options(
        "/chat",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED


def test_disallowed_origin_gets_no_preflight_approval():
    response = client.options(
        "/chat",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_the_real_response_carries_the_header_too(monkeypatch):
    """A preflight passing is not enough — the browser also checks the actual
    response, and this is exactly the gap that shipped without a test."""
    monkeypatch.setattr(rag, "retrieve", lambda question, k=6: [])
    monkeypatch.setattr(
        rag,
        "get_client",
        lambda: type(
            "_Client",
            (),
            {
                "messages": type(
                    "_Messages",
                    (),
                    {"create": staticmethod(lambda **kw: FakeMessage(content=[FakeTextBlock("An answer.")]))},
                )()
            },
        )(),
    )

    response = client.post(
        "/chat",
        json={"question": "Who does he work for?"},
        headers={"Origin": ALLOWED},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
