"""Tests for Sentry wiring, with the transport mocked.

The point of most of these is the privacy posture: this backend handles a
stranger's name, email and message, and a visitor's questions, and none of it
may leave the VM inside an error report. `scrub_event` is a pure function, so
that half needs no mocking at all. The init path is checked against a fake SDK
so no real `sentry_sdk.init` ever runs and nothing is ever sent.
"""

from __future__ import annotations

import pytest

from app import main, observability


# --- The scrubber -----------------------------------------------------------


def test_the_request_body_is_removed():
    """A /contact body is a real person's details; a /chat body a question."""
    event = {"request": {"data": {"email": "dana@example.com", "message": "hire me"}}}
    scrubbed = observability.scrub_event(event, {})
    assert "data" not in scrubbed["request"]


def test_cookies_and_query_string_are_removed():
    event = {"request": {"cookies": {"session": "abc"}, "query_string": "q=secret"}}
    scrubbed = observability.scrub_event(event, {})
    assert "cookies" not in scrubbed["request"]
    assert "query_string" not in scrubbed["request"]


def test_sensitive_headers_are_dropped_but_others_kept():
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret",
                "Cookie": "session=abc",
                "X-Real-IP": "203.0.113.7",
                "X-Forwarded-For": "203.0.113.7",
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/json",
            }
        }
    }
    headers = observability.scrub_event(event, {})["request"]["headers"]

    assert "Authorization" not in headers
    assert "Cookie" not in headers
    assert "X-Real-IP" not in headers
    assert "X-Forwarded-For" not in headers
    # Non-identifying headers are diagnostically useful and stay.
    assert headers["User-Agent"] == "Mozilla/5.0"
    assert headers["Content-Type"] == "application/json"


def test_header_scrubbing_is_case_insensitive():
    """Sentry may normalise header case; the scrub must not depend on it."""
    event = {"request": {"headers": {"AUTHORIZATION": "Bearer secret", "cookie": "x"}}}
    headers = observability.scrub_event(event, {})["request"]["headers"]
    assert headers == {}


def test_client_ip_is_removed_from_user():
    event = {"user": {"ip_address": "203.0.113.7", "id": "anon"}}
    scrubbed = observability.scrub_event(event, {})
    assert "ip_address" not in scrubbed["user"]


def test_the_stack_trace_survives_scrubbing():
    """Scrubbing must remove personal data, not the thing that makes an error useful."""
    event = {
        "exception": {"values": [{"type": "RuntimeError", "value": "boom"}]},
        "request": {"data": {"secret": "x"}, "url": "http://vm/chat"},
    }
    scrubbed = observability.scrub_event(event, {})
    assert scrubbed["exception"]["values"][0]["type"] == "RuntimeError"
    assert scrubbed["request"]["url"] == "http://vm/chat"  # the path is not PII
    assert "data" not in scrubbed["request"]


def test_scrubbing_an_event_with_no_request_is_a_no_op():
    event = {"exception": {"values": []}}
    assert observability.scrub_event(event, {}) == event


# --- Initialisation ---------------------------------------------------------


def test_init_is_a_no_op_without_a_dsn(monkeypatch):
    """No DSN locally and in tests, so nothing is ever sent from here."""
    monkeypatch.setattr(observability, "SENTRY_DSN", "")
    assert observability.init_sentry() is False


def test_init_configures_the_sdk_when_a_dsn_is_set(monkeypatch):
    monkeypatch.setattr(observability, "SENTRY_DSN", "https://key@example.ingest.sentry.io/1")
    monkeypatch.setattr(observability, "SENTRY_ENVIRONMENT", "production")

    captured = {}
    import sentry_sdk

    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: captured.update(kwargs))

    assert observability.init_sentry() is True
    assert captured["dsn"] == "https://key@example.ingest.sentry.io/1"
    assert captured["environment"] == "production"


def test_init_disables_pii(monkeypatch):
    """The single most important setting: no personal data attached by default."""
    monkeypatch.setattr(observability, "SENTRY_DSN", "https://key@example.ingest.sentry.io/1")

    captured = {}
    import sentry_sdk

    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: captured.update(kwargs))
    observability.init_sentry()

    assert captured["send_default_pii"] is False


def test_init_installs_the_scrubber_on_both_channels(monkeypatch):
    """Errors and performance transactions both carry request data to scrub."""
    monkeypatch.setattr(observability, "SENTRY_DSN", "https://key@example.ingest.sentry.io/1")

    captured = {}
    import sentry_sdk

    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: captured.update(kwargs))
    observability.init_sentry()

    assert captured["before_send"] is observability.scrub_event
    assert captured["before_send_transaction"] is observability.scrub_event


# --- The deliberate-error endpoint ------------------------------------------


def test_debug_error_raises():
    """The endpoint the VERIFY step triggers. It must actually raise."""
    from fastapi.testclient import TestClient

    # raise_server_exceptions=False so the TestClient surfaces the 500 the way a
    # real client would, rather than re-raising into the test.
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.get("/debug/error")
    assert response.status_code == 500


def test_debug_error_is_hidden_from_the_schema():
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    schema = client.get("/openapi.json").json()
    assert "/debug/error" not in schema["paths"]


def test_debug_error_carries_no_request_data():
    """Triggering it must reveal nothing — the message is a fixed string."""
    import inspect

    source = inspect.getsource(main.debug_error)
    assert "Deliberate test error" in source
    # It takes no parameters, so there is nothing from the request to leak.
    assert inspect.signature(main.debug_error).parameters == {}
