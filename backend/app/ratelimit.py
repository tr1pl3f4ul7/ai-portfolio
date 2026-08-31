"""Daily request ceilings for /chat and /contact.

One ceiling per endpoint, counted per UTC calendar day.

There used to be a second, per-client-IP ceiling on each. It existed because
every request spent money at the Claude API: the total was the spend cap, and
the per-IP limit was what stopped one visitor draining it. Z.AI's free models
are not metered by volume at all — only by concurrency — so there is no budget
left to drain and that counter was guarding nothing.

What remains is not a spend cap. `/contact` still sends mail through Resend,
which has its own free-tier ceiling, so the total below is what keeps this
service inside it. Abuse control for that endpoint belongs at the edge, in front
of the VM, rather than in a counter here.

State lives in memory. That is a deliberate choice, not an oversight:

- One uvicorn worker serves this site, so there is one counter and it is
  authoritative. Adding workers would silently multiply the effective limits,
  which is worth remembering before anyone tunes the systemd unit.
- A restart resets the counters. The failure mode is a few extra requests after
  a deploy, which is cheaper than adding Redis to a 12 GB box.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from app.config import CHAT_DAILY_LIMIT_TOTAL


class RateLimited(Exception):
    """The caller hit the daily ceiling."""

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
    """A request counter that rolls over at UTC midnight.

    `clock` is injectable purely so tests can cross a day boundary without
    waiting for one.
    """

    def __init__(
        self,
        total_limit: int = CHAT_DAILY_LIMIT_TOTAL,
        clock=_utc_now,
    ) -> None:
        self._total_limit = total_limit
        self._clock = clock
        self._lock = Lock()
        self._day = None
        self._total = 0

    def check_and_count(self) -> None:
        """Record one request, or raise RateLimited if the day is spent.

        Counting and checking are one operation under one lock — splitting them
        would let two concurrent requests both pass the check on the last
        remaining slot.
        """
        now = self._clock()
        today = now.date()

        with self._lock:
            if today != self._day:
                # New day: drop yesterday's count entirely rather than decay it.
                self._day = today
                self._total = 0

            if self._total >= self._total_limit:
                raise RateLimited("global", self._total_limit, seconds_until_reset(now))

            self._total += 1
