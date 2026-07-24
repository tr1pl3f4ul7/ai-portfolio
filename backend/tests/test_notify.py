"""Tests for the Resend request itself.

The body-building is covered indirectly through test_contact.py; what those
cannot reach is the outgoing HTTP request, because the autouse guard replaces
`_post`. These test `_build_request`, which the guard leaves alone — and they
exist because a missing header (User-Agent) is precisely what broke delivery
during the Step 2.4 smoke test.
"""

from __future__ import annotations

from app import notify


def test_the_request_carries_a_named_user_agent():
    """urllib's default Python-urllib/x.y is banned by Cloudflare (error 1010)."""
    request = notify._build_request({"to": ["someone@example.com"]})
    user_agent = request.get_header("User-agent")

    assert user_agent == notify.USER_AGENT
    assert "python-urllib" not in user_agent.lower()


def test_the_request_is_an_authenticated_json_post():
    request = notify._build_request({"to": ["someone@example.com"]})

    assert request.method == "POST"
    assert request.full_url == notify.RESEND_ENDPOINT
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("Authorization", "").startswith("Bearer ")
