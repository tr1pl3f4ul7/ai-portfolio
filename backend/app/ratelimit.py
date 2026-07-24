"""Daily rate limiting for /chat.

Two ceilings, both counted per UTC calendar day: one per client IP, one across
everyone. Every /chat request spends real money at the Claude API, so the total
is the spend cap and the per-IP limit is what stops one visitor consuming it.

State lives in memory. That is a deliberate choice, not an oversight:

- One uvicorn worker serves this site, so there is one counter and it is
  authoritative. Adding workers would silently multiply the effective limits,
  which is worth remembering before anyone tunes the systemd unit.
- A restart resets the counters. The failure mode is a few extra requests after
  a deploy, which is cheaper than adding Redis to a 12 GB box.

Both limits reject with the same 429, distinguished by `scope`, so the client
can tell "you personally have had enough" from "the site has had enough today".
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from app.config import CHAT_DAILY_LIMIT_PER_IP, CHAT_DAILY_LIMIT_TOTAL


class RateLimited(Exception):
    """A caller hit one of the two ceilings."""

    def __init__(self, scope: str, limit: int, retry_after: int) -> None:
        self.scope = scope
        self.limit = limit
        self.retry_after = retry_after
        super().__init__(f"{scope} limit of {limit} requests per day reached")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def seconds_until_reset(now: datetime) -> int:
    """Whole seconds until the next UTC midnight, for the Retry-After header."""
    tomorrow = now.date().toordinal() + 1
    midnight = datetime.fromordinal(tomorrow).replace(tzinfo=timezone.utc)
    return max(1, int((midnight - now).total_seconds()))


class DailyRateLimiter:
    """Per-IP and global request counters that roll over at UTC midnight.

    `clock` is injectable purely so tests can cross a day boundary without
    waiting for one.
    """

    def __init__(
        self,
        per_ip_limit: int = CHAT_DAILY_LIMIT_PER_IP,
        total_limit: int = CHAT_DAILY_LIMIT_TOTAL,
        clock=_utc_now,
    ) -> None:
        self._per_ip_limit = per_ip_limit
        self._total_limit = total_limit
        self._clock = clock
        self._lock = Lock()
        self._day = None
        self._total = 0
        self._per_ip: dict[str, int] = {}

    def check_and_count(self, ip: str) -> None:
        """Record one request from `ip`, or raise RateLimited if it is over.

        Counting and checking are one operation under one lock — splitting them
        would let two concurrent requests both pass the check on the last
        remaining slot.
        """
        now = self._clock()
        today = now.date()

        with self._lock:
            if today != self._day:
                # New day: drop yesterday's counters entirely rather than decay
                # them, and drop the per-IP dict with them so it cannot grow
                # without bound over a long uptime.
                self._day = today
                self._total = 0
                self._per_ip = {}

            if self._total >= self._total_limit:
                raise RateLimited("global", self._total_limit, seconds_until_reset(now))

            used = self._per_ip.get(ip, 0)
            if used >= self._per_ip_limit:
                raise RateLimited("per-ip", self._per_ip_limit, seconds_until_reset(now))

            self._per_ip[ip] = used + 1
            self._total += 1


def client_ip(request) -> str:
    """Best available client address for a request arriving through nginx.

    `X-Real-IP` is what nginx sets from the socket peer, overwriting anything
    the caller sent, so it is trustworthy. `X-Forwarded-For` is a list a client
    can prepend to, but nginx's `$proxy_add_x_forwarded_for` appends the real
    peer at the end — so the RIGHTMOST entry is the one our own proxy wrote and
    the only one that cannot be spoofed. Never take the leftmost.

    With no proxy in front (local dev, the test client) both headers are absent
    and the socket address is already correct.
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.rsplit(",", 1)[-1].strip()

    return request.client.host if request.client else "unknown"
