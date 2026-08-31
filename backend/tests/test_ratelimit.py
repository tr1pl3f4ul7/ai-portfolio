"""Tests for the daily rate limiter and its wiring into POST /chat.

One ceiling per endpoint, per UTC calendar day. The limiter unit tests use an
injected clock so a day boundary can be crossed without waiting for one.

The per-client-IP ceiling that used to sit alongside the total is gone, along
with the tests that covered it: it existed to stop one visitor draining a paid
budget, and Z.AI's free models are not metered by volume. Abuse control for
/contact moved to the edge.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main, rag
from app.ratelimit import DailyRateLimiter, RateLimited, seconds_until_reset
from app.store import SearchResult
from tests.conftest import zai_response

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


def test_requests_under_the_limit_are_allowed():
    limiter = DailyRateLimiter(total_limit=3, clock=FakeClock(NOON))
    for _ in range(3):
        limiter.check_and_count()


def test_the_limit_stops_the_next_request():
    limiter = DailyRateLimiter(total_limit=2, clock=FakeClock(NOON))
    limiter.check_and_count()
    limiter.check_and_count()

    with pytest.raises(RateLimited) as exc:
        limiter.check_and_count()
    assert exc.value.scope == "global"
    assert exc.value.limit == 2


def test_the_limit_holds_regardless_of_who_is_calling():
    """No per-caller identity any more: the total is the only ceiling."""
    limiter = DailyRateLimiter(total_limit=3, clock=FakeClock(NOON))
    for _ in range(3):
        limiter.check_and_count()

    with pytest.raises(RateLimited):
        limiter.check_and_count()


def test_rejected_requests_are_not_counted():
    """Otherwise a blocked caller would keep pushing the reset further away."""
    limiter = DailyRateLimiter(total_limit=1, clock=FakeClock(NOON))
    limiter.check_and_count()
    for _ in range(5):
        with pytest.raises(RateLimited):
            limiter.check_and_count()

    assert limiter._total == 1


def test_counters_reset_at_the_next_utc_day():
    clock = FakeClock(NOON)
    limiter = DailyRateLimiter(total_limit=1, clock=clock)
    limiter.check_and_count()
    with pytest.raises(RateLimited):
        limiter.check_and_count()

    clock.advance(hours=13)  # past midnight UTC
    limiter.check_and_count()


def test_counters_do_not_reset_before_midnight():
    clock = FakeClock(NOON)
    limiter = DailyRateLimiter(total_limit=1, clock=clock)
    limiter.check_and_count()

    clock.advance(hours=11, minutes=59)  # 23:59 the same UTC day
    with pytest.raises(RateLimited):
        limiter.check_and_count()


def test_seconds_until_reset_counts_down_to_midnight():
    assert seconds_until_reset(NOON) == 12 * 60 * 60
    assert seconds_until_reset(datetime(2026, 7, 24, 23, 59, 30, tzinfo=timezone.utc)) == 30


def test_seconds_until_reset_is_never_zero():
    """Retry-After: 0 would invite an immediate retry that also fails."""
    midnight = datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc)
    assert seconds_until_reset(midnight - timedelta(microseconds=1)) >= 1


# --- Wiring into the endpoint -----------------------------------------------


@pytest.fixture
def answering(monkeypatch, fake_llm):
    """A /chat that succeeds, so the only thing under test is the limiter.

    Returns the model call log, so a test can assert the limiter ran *before*
    the request reached the model.
    """
    monkeypatch.setattr(
        rag,
        "retrieve",
        lambda question, k=6: [
            SearchResult(source="about.md", heading="Who he is", text="...", distance=0.1)
        ],
    )
    return fake_llm(zai_response("An answer."))


def _ask():
    return client.post("/chat", json={"question": "Who does he work for?"})


def test_chat_returns_429_once_the_daily_total_is_spent(answering, monkeypatch):
    monkeypatch.setattr(main, "limiter", DailyRateLimiter(total_limit=2))

    assert _ask().status_code == 200
    assert _ask().status_code == 200

    response = _ask()
    assert response.status_code == 429
    assert "global" in response.json()["detail"]


def test_chat_429_carries_a_retry_after_header(answering, monkeypatch):
    monkeypatch.setattr(main, "limiter", DailyRateLimiter(total_limit=0))

    response = _ask()
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


def test_a_rate_limited_request_never_reaches_the_model(answering, monkeypatch):
    """The check must run first, so a refused request never takes the single
    concurrency slot the model allows."""
    monkeypatch.setattr(main, "limiter", DailyRateLimiter(total_limit=0))

    assert _ask().status_code == 429
    assert answering == []


def test_chat_and_contact_do_not_share_a_counter(answering, monkeypatch):
    """Chat traffic must never be able to close the contact form."""
    monkeypatch.setattr(main, "limiter", DailyRateLimiter(total_limit=0))
    monkeypatch.setattr(main, "contact_limiter", DailyRateLimiter(total_limit=5))

    assert _ask().status_code == 429
    assert main.contact_limiter._total == 0


def test_health_is_not_rate_limited(monkeypatch):
    """The uptime monitor polls constantly; it must never be throttled."""
    monkeypatch.setattr(main, "limiter", DailyRateLimiter(total_limit=0))
    for _ in range(5):
        assert client.get("/health").status_code == 200
