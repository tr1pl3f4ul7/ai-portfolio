"""Z.AI GLM API client.

The one place in the backend that talks to a language model. `/chat`
(app/rag.py) and contact triage (app/triage.py) both come through `complete`.

There is no vendor SDK here on purpose: Z.AI's chat-completions endpoint is a
bearer token, a JSON body and a JSON response, so `httpx` is the whole client.
That is a smaller dependency than the SDK it replaced, and it keeps the wire
format visible in this file rather than behind someone else's abstraction.

Two exceptions leave this module, and callers map them to their own:

- `LLMUnavailable` — we could not get an answer. The message is always safe to
  show a visitor: a status code, never a response body. Z.AI echoes request
  content back in some error bodies, and for `/contact` that content is a
  stranger's message.
- `LLMRefused` — we reached the model and it declined. Distinct because it is
  not a failure of ours, and because `/chat` and triage word it differently.

---

One model, two retry budgets. The numbers behind them were measured against the
live API, not guessed: of eight sequential calls to GLM-4.7-Flash, two returned
an answer and six returned `429 / code 1305 "service temporarily overloaded"`.
Free on Z.AI means shared best-effort capacity.

What makes that survivable is the *shape* of the failure. An overloaded 429
comes back in about 0.4s where a real answer takes 1-2s, so an attempt that
fails costs almost nothing. Retrying is therefore the whole strategy, and the
only question is how long each caller can afford to keep trying:

`FAST` — /chat, where a visitor is watching. Ten attempts under a ten-second
deadline, reaching roughly 95%. The deadline is what protects them: better an
honest 503 at ten seconds than a spinner that never resolves.

`PATIENT` — contact triage, which runs in a background task after the sender
already has their 200. Nobody is waiting, so it can keep trying for two minutes
and reach a success rate that rounds to certainty. This is the reason triage
moved off the request path (app/main.py): not because the model is slow, but
because being unwatched is what makes retrying this hard acceptable.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.config import ZAI_API_KEY, ZAI_BASE_URL, ZAI_MODEL


class LLMUnavailable(Exception):
    """No answer could be obtained. Safe to surface; carries no response body."""


class LLMRefused(Exception):
    """The model was reached and declined to answer."""


@dataclass(frozen=True)
class Profile:
    """How hard to try, and how long, for one class of call."""

    max_attempts: int
    deadline: float
    read_timeout: float


# /chat. A visitor is watching, so the budget is what they will tolerate.
#
# 15s rather than 10s, and the difference is not arbitrary. Measured end to end
# through this retry loop, successful calls landed at 1.4, 2.5, 3.5, 6.8 and
# 10.1 seconds — a median around 3s with a long tail. A 10s deadline was
# amputating exactly that tail and turning calls that were about to succeed into
# 503s. Free-tier capacity also swings widely minute to minute: the same profile
# measured 5/5 in one run and 2/4 a minute earlier.
#
# `read_timeout` must stay comfortably under `deadline`, or a single hung
# request outlasts the entire budget and there is no retry left to make — which
# is what made timeouts effectively fatal before they were retryable. 10s is
# still several times any single call observed (a lone generation is 1-2s; the
# 10s figures above are whole retry loops, not one request).
FAST = Profile(max_attempts=14, deadline=15.0, read_timeout=10.0)

# Contact triage. Runs in a background task with nobody waiting, so it can keep
# going long past what an endpoint could. At a 1-in-4 success rate, forty
# attempts fail together about once in a hundred thousand times.
#
# 30s per request rather than 60s for the same reason: four hung requests should
# each be abandoned and retried inside the budget, not two of them consume all
# of it.
PATIENT = Profile(max_attempts=40, deadline=120.0, read_timeout=30.0)


# Statuses worth trying again. 429 is the one that actually happens — it is how
# both the concurrency limit and free-tier overload present.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

# Backoff between attempts: exponential, capped, and jittered so that two
# visitors who collide do not then retry in lockstep forever.
_BACKOFF_BASE = 0.3
_BACKOFF_CAP = 1.5


def _wait(seconds: float) -> None:
    """Indirection so tests can run the retry path without actually sleeping."""
    time.sleep(seconds)


def _backoff(attempt: int) -> float:
    return min(_BACKOFF_CAP, _BACKOFF_BASE * (2**attempt)) * (0.5 + random.random() / 2)


@lru_cache(maxsize=1)
def get_client() -> httpx.Client:
    """Return the shared HTTP client.

    Cached because constructing one opens a connection pool, and a TLS handshake
    per attempt would be dead time on a path that already expects to retry.
    Per-request timeouts are passed at call time, since the two profiles want
    very different ones.
    """
    if not ZAI_API_KEY:
        raise LLMUnavailable("ZAI_API_KEY is not set")

    return httpx.Client(
        base_url=ZAI_BASE_URL,
        headers={
            "Authorization": f"Bearer {ZAI_API_KEY}",
            "Content-Type": "application/json",
        },
    )


def _post(payload: dict, read_timeout: float) -> httpx.Response:
    """POST one chat-completions request.

    Split out from `complete` so the test suite has a single seam to replace —
    the same arrangement as `notify._post`. Nothing here interprets the result.
    """
    return get_client().post(
        "/chat/completions",
        json=payload,
        timeout=httpx.Timeout(read_timeout, connect=10.0),
    )


def complete(
    system: str,
    user: str,
    *,
    max_tokens: int,
    profile: Profile = FAST,
    json_object: bool = False,
) -> str:
    """Send one system+user turn and return the assistant's text.

    `json_object` asks Z.AI to guarantee syntactically valid JSON. It does not
    enforce a schema — that is the caller's job, and app/triage.py does it.
    """
    payload: dict = {
        "model": ZAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        # GLM-4.7-Flash is a reasoning model, and its hidden `reasoning_content`
        # is billed against `max_tokens` *before* a single token of answer is
        # emitted. Measured: "Say ready." spent 96 reasoning tokens to produce a
        # 4-token reply, and at max_tokens=16 returned finish_reason="length"
        # with content completely empty.
        #
        # Left on, that silently breaks both callers — a /chat answer truncated
        # mid-sentence, or triage returning half a JSON object that then fails
        # validation — and it breaks them *intermittently*, on exactly the long
        # questions where thinking runs longest.
        #
        # Neither job here is a reasoning problem: one summarises context that
        # has already been retrieved and ranked, the other classifies a short
        # message. Disabling it took the same call from 96 reasoning tokens to 0.
        # `reasoning_effort: "minimal"` is not the lever — it still spent 82.
        "thinking": {"type": "disabled"},
    }
    if json_object:
        payload["response_format"] = {"type": "json_object"}

    started = time.monotonic()
    response: httpx.Response | None = None
    transport_failure: str | None = None

    for attempt in range(profile.max_attempts):
        transport_failure = None
        try:
            response = _post(payload, profile.read_timeout)
        except httpx.TimeoutException:
            # Retried, exactly like a 429. On a shared best-effort tier a hung
            # request is no less ordinary than a rejected one, and treating it
            # as fatal while retrying the 429 was an asymmetry with nothing
            # behind it — observed in production as a 503 on the first attempt
            # where a second would very likely have answered.
            response, transport_failure = None, "the Z.AI API timed out"
        except httpx.TransportError:
            response, transport_failure = None, "could not reach the Z.AI API"

        # An answer, or a refusal there is no point repeating.
        if response is not None and response.status_code not in _RETRY_STATUSES:
            break
        if attempt == profile.max_attempts - 1:
            break
        # Stop early rather than start an attempt that would blow the budget.
        if time.monotonic() - started >= profile.deadline:
            break
        _wait(_backoff(attempt))

    if response is None:
        raise LLMUnavailable(transport_failure or "the Z.AI API could not be reached")

    if response.status_code == 429:
        raise LLMUnavailable("the Z.AI API is rate limiting this service")
    if response.status_code != 200:
        # The status only. Z.AI's error bodies can quote the request back, and
        # for /contact the request is a stranger's name, email and message.
        raise LLMUnavailable(f"the Z.AI API returned {response.status_code}")

    try:
        body = response.json()
        choice = body["choices"][0]
    except (ValueError, KeyError, IndexError) as exc:
        raise LLMUnavailable("the Z.AI API returned an unreadable response") from exc

    # GLM reports a content filter as a finish_reason rather than an error
    # status, so this has to be checked before reading the content — which is
    # empty or partial in that case.
    if choice.get("finish_reason") == "sensitive":
        raise LLMRefused("the model declined the request")

    return (choice.get("message") or {}).get("content", "").strip()
