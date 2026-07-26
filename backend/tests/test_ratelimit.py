"""Tests for the daily rate limiter and its wiring into POST /chat.

Two ceilings, both per UTC calendar day: one per client IP, one across everyone.
The limiter unit tests use an injected clock so a day boundary can be crossed
without waiting for one.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from app import main, rag
from app.ratelimit import DailyRateLimiter, RateLimited, client_ip, seconds_until_reset
from app.store import SearchResult
from tests.conftest import FakeMessage, FakeTextBlock

client = TestClient(main.app)

NOON = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


# --- The limiter ------------------------------------------------------------


def test_requests_under_both_limits_are_allowed():
    limiter = DailyRateLimiter(per_ip_limit=3, total_limit=10, clock=FakeClock(NOON))
    for _ in range(3):
        limiter.check_and_count("1.1.1.1")


def test_per_ip_limit_stops_one_visitor():
    limiter = DailyRateLimiter(per_ip_limit=2, total_limit=10, clock=FakeClock(NOON))
    limiter.check_and_count("1.1.1.1")
    limiter.check_and_count("1.1.1.1")

    with pytest.raises(RateLimited) as exc:
        limiter.check_and_count("1.1.1.1")
    assert exc.value.scope == "per-ip"
    assert exc.value.limit == 2


def test_one_blocked_visitor_does_not_block_another():
    limiter = DailyRateLimiter(per_ip_limit=1, total_limit=10, clock=FakeClock(NOON))
    limiter.check_and_count("1.1.1.1")

    with pytest.raises(RateLimited):
        limiter.check_and_count("1.1.1.1")
    limiter.check_and_count("2.2.2.2")  # unaffected


def test_global_limit_holds_across_many_addresses():
    """The point of the total: spreading traffic over IPs must not evade it."""
    limiter = DailyRateLimiter(per_ip_limit=100, total_limit=3, clock=FakeClock(NOON))
    for i in range(3):
        limiter.check_and_count(f"10.0.0.{i}")

    with pytest.raises(RateLimited) as exc:
        limiter.check_and_count("10.0.0.99")
    assert exc.value.scope == "global"
    assert exc.value.limit == 3


def test_global_limit_is_checked_before_the_per_ip_one():
    """Once the site's budget is spent, every caller gets the same answer."""
    limiter = DailyRateLimiter(per_ip_limit=5, total_limit=1, clock=FakeClock(NOON))
    limiter.check_and_count("1.1.1.1")

    with pytest.raises(RateLimited) as exc:
        limiter.check_and_count("1.1.1.1")
    assert exc.value.scope == "global"


def test_rejected_requests_are_not_counted():
    """Otherwise a blocked caller would keep pushing the reset further away."""
    clock = FakeClock(NOON)
    limiter = DailyRateLimiter(per_ip_limit=1, total_limit=10, clock=clock)
    limiter.check_and_count("1.1.1.1")
    for _ in range(5):
        with pytest.raises(RateLimited):
            limiter.check_and_count("1.1.1.1")

    assert limiter._total == 1


def test_counters_reset_at_the_next_utc_day():
    clock = FakeClock(NOON)
    limiter = DailyRateLimiter(per_ip_limit=1, total_limit=1, clock=clock)
    limiter.check_and_count("1.1.1.1")
    with pytest.raises(RateLimited):
        limiter.check_and_count("1.1.1.1")

    clock.advance(hours=13)  # past midnight UTC
    limiter.check_and_count("1.1.1.1")


def test_counters_do_not_reset_before_midnight():
    clock = FakeClock(NOON)
    limiter = DailyRateLimiter(per_ip_limit=1, total_limit=5, clock=clock)
    limiter.check_and_count("1.1.1.1")

    clock.advance(hours=11, minutes=59)  # 23:59 the same UTC day
    with pytest.raises(RateLimited):
        limiter.check_and_count("1.1.1.1")


def test_per_ip_table_is_dropped_on_rollover():
    """Long uptime must not grow an unbounded dict of yesterday's visitors."""
    clock = FakeClock(NOON)
    limiter = DailyRateLimiter(per_ip_limit=5, total_limit=100, clock=clock)
    for i in range(50):
        limiter.check_and_count(f"10.0.0.{i}")

    clock.advance(days=1)
    limiter.check_and_count("1.1.1.1")

    assert limiter._per_ip == {"1.1.1.1": 1}


def test_seconds_until_reset_counts_down_to_midnight():
    assert seconds_until_reset(NOON) == 12 * 60 * 60
    assert seconds_until_reset(datetime(2026, 7, 24, 23, 59, 30, tzinfo=timezone.utc)) == 30


def test_seconds_until_reset_is_never_zero():
    """Retry-After: 0 would invite an immediate retry that also fails."""
    midnight = datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc)
    assert seconds_until_reset(midnight - timedelta(microseconds=1)) >= 1


# --- Identifying the caller -------------------------------------------------


class FakeRequest:
    def __init__(self, headers=None, host="127.0.0.1"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": host})() if host else None


def test_socket_address_is_used_when_there_is_no_proxy():
    assert client_ip(FakeRequest(host="203.0.113.7")) == "203.0.113.7"


def test_x_real_ip_is_preferred():
    request = FakeRequest({"x-real-ip": "203.0.113.7"}, host="127.0.0.1")
    assert client_ip(request) == "203.0.113.7"


def test_rightmost_forwarded_for_entry_is_used():
    """nginx appends the real peer last; earlier entries are caller-supplied."""
    request = FakeRequest({"x-forwarded-for": "1.2.3.4, 5.6.7.8, 203.0.113.7"})
    assert client_ip(request) == "203.0.113.7"


def test_a_spoofed_forwarded_for_cannot_change_the_identity():
    """Two visitors faking the same left-hand entry still count separately."""
    a = client_ip(FakeRequest({"x-forwarded-for": "9.9.9.9, 203.0.113.1"}))
    b = client_ip(FakeRequest({"x-forwarded-for": "9.9.9.9, 203.0.113.2"}))
    assert a != b


def test_missing_client_falls_back_to_a_placeholder():
    assert client_ip(FakeRequest(host=None)) == "unknown"


# --- Wiring into the endpoint -----------------------------------------------


@pytest.fixture
def answering(monkeypatch):
    """A /chat that succeeds, so the only thing under test is the limiter."""
    monkeypatch.setattr(
        rag,
        "retrieve",
        lambda question, k=6: [
            SearchResult(source="about.md", heading="Who he is", text="...", distance=0.1)
        ],
    )
    monkeypatch.setattr(rag, "get_client", lambda: _AlwaysAnswers())


class _AlwaysAnswers:
    class messages:
        # A shared collector, not a per-instance default — messages is used as
        # a static namespace and never instantiated.
        calls: ClassVar[list] = []

        @staticmethod
        def create(**kwargs):
            _AlwaysAnswers.messages.calls.append(kwargs)
            return FakeMessage(content=[FakeTextBlock("An answer.")])


def _ask(ip: str = "203.0.113.7"):
    return client.post(
        "/chat", json={"question": "Who does he work for?"}, headers={"X-Real-IP": ip}
    )


def test_chat_returns_429_once_the_ip_is_over_its_limit(answering, monkeypatch):
    monkeypatch.setattr(main, "limiter", DailyRateLimiter(per_ip_limit=2, total_limit=100))

    assert _ask().status_code == 200
    assert _ask().status_code == 200

    response = _ask()
    assert response.status_code == 429
    assert "per-ip" in response.json()["detail"]


def test_chat_429_carries_a_retry_after_header(answering, monkeypatch):
    monkeypatch.setattr(main, "limiter", DailyRateLimiter(per_ip_limit=0, total_limit=100))

    response = _ask()
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


def test_chat_returns_429_once_the_site_total_is_spent(answering, monkeypatch):
    monkeypatch.setattr(main, "limiter", DailyRateLimiter(per_ip_limit=100, total_limit=1))

    assert _ask("203.0.113.1").status_code == 200

    response = _ask("203.0.113.2")
    assert response.status_code == 429
    assert "global" in response.json()["detail"]


def test_a_rate_limited_request_never_reaches_claude(answering, monkeypatch):
    """The limit exists to stop spend, so it must run before the API call."""
    monkeypatch.setattr(main, "limiter", DailyRateLimiter(per_ip_limit=0, total_limit=100))
    _AlwaysAnswers.messages.calls = []

    assert _ask().status_code == 429
    assert _AlwaysAnswers.messages.calls == []


def test_the_limit_is_per_ip_not_global_by_accident(answering, monkeypatch):
    monkeypatch.setattr(main, "limiter", DailyRateLimiter(per_ip_limit=1, total_limit=100))

    assert _ask("203.0.113.1").status_code == 200
    assert _ask("203.0.113.1").status_code == 429
    assert _ask("203.0.113.2").status_code == 200


def test_health_is_not_rate_limited(monkeypatch):
    """The uptime monitor polls constantly; it must never be throttled."""
    monkeypatch.setattr(main, "limiter", DailyRateLimiter(per_ip_limit=0, total_limit=0))
    for _ in range(5):
        assert client.get("/health").status_code == 200
