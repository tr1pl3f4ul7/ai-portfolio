"""Shared test fixtures, and the guards that keep the suite offline.

Two autouse guards apply to every test in this directory:

- `no_live_llm_call` replaces the POST inside `app.llm` with one that refuses
  to run.
- `no_live_resend_call` replaces the raw POST inside `app.notify` with one that
  refuses to run.

Between them, any code path that would reach the network fails loudly with a
clear message instead of quietly calling a real API or emailing a real person —
the CLAUDE.md rule made mechanical rather than remembered.

Tests that need either use the `fake_llm` or `fake_resend` fixture; neither goes
near the replaced functions.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# This block MUST run before `app` is imported, and cannot be a fixture.
#
# config.py reads os.environ at import time, and main.py calls
# observability.init_sentry() at import time too — both happen while pytest is
# collecting test modules, which is long before any fixture executes. Setting
# these here, at conftest module scope, is the only point early enough.
#
# Sentry in particular: without this the suite initialises against the real DSN
# and posts test exceptions to the live project. That was observed, not
# theorised — an empty DSN disables it, which is what tests must always use.
#
# load_dotenv(override=False) in config.py will not overwrite an existing value,
# so setting these wins over backend/.env.
# ---------------------------------------------------------------------------
DUMMY_ZAI_KEY = "zai-TEST-KEY-NOT-REAL"
DUMMY_RESEND_KEY = "re_TEST_KEY_NOT_REAL"

# Captured before the dummy overwrites it, because `-m live` tests need the real
# one and this is the last moment it is still in the environment. In CI it comes
# from the GitHub Actions secret; locally, from backend/.env, which config.py has
# not read yet at this point — so read it here rather than importing config.
REAL_ZAI_KEY = os.environ.get("ZAI_API_KEY", "")
if not REAL_ZAI_KEY:
    from dotenv import dotenv_values

    REAL_ZAI_KEY = dotenv_values(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    ).get("ZAI_API_KEY", "")

os.environ["ZAI_API_KEY"] = DUMMY_ZAI_KEY
os.environ["RESEND_API_KEY"] = DUMMY_RESEND_KEY
os.environ["CONTACT_NOTIFY_TO"] = "nobody@example.com"
os.environ["SENTRY_DSN"] = ""

import httpx
import pytest

from app import config, llm, notify, observability


class LiveApiCallAttempted(AssertionError):
    """Raised if a test tries to reach the real Z.AI API or Resend."""


@pytest.fixture(autouse=True)
def no_real_credentials(request, monkeypatch):
    """Belt to the module-level braces above.

    Steps aside for `-m live` tests, which exist precisely to use the real key —
    and skips them outright if there isn't one, rather than letting them fail as
    though the code were broken.

    The environment is already clean by the time this runs; what this covers is
    the *bound copies* — modules that did `from app.config import X` hold their
    own reference, so patching the environment alone would not reach them.

    Why both layers: a failing assertion renders the locals of the frame it
    failed in, which is exactly how a real key reached a terminal once already.
    Removing the credential from the process beats intercepting its use.
    """
    if "live" in request.keywords:
        if not REAL_ZAI_KEY:
            pytest.skip("ZAI_API_KEY is not set — live tests need a real key")
        monkeypatch.setattr(config, "ZAI_API_KEY", REAL_ZAI_KEY)
        monkeypatch.setattr(llm, "ZAI_API_KEY", REAL_ZAI_KEY)
        llm.get_client.cache_clear()
        # Resend stays fake even here. Nothing in the live suite should email
        # a real person.
        monkeypatch.setattr(notify, "RESEND_API_KEY", DUMMY_RESEND_KEY)
        monkeypatch.setattr(notify, "CONTACT_NOTIFY_TO", "nobody@example.com")
        monkeypatch.setattr(observability, "SENTRY_DSN", "")
        return

    monkeypatch.setattr(config, "ZAI_API_KEY", DUMMY_ZAI_KEY)
    monkeypatch.setattr(config, "RESEND_API_KEY", DUMMY_RESEND_KEY)
    monkeypatch.setattr(config, "SENTRY_DSN", "")
    monkeypatch.setattr(llm, "ZAI_API_KEY", DUMMY_ZAI_KEY)
    monkeypatch.setattr(notify, "RESEND_API_KEY", DUMMY_RESEND_KEY)
    monkeypatch.setattr(notify, "CONTACT_NOTIFY_TO", "nobody@example.com")
    monkeypatch.setattr(observability, "SENTRY_DSN", "")


@pytest.fixture(autouse=True)
def no_live_llm_call(request, monkeypatch):
    """Stop any test from actually calling Z.AI. Except the ones marked `live`."""
    if "live" in request.keywords:
        llm.get_client.cache_clear()
        yield
        return

    def _refuse(*args, **kwargs):
        raise LiveApiCallAttempted(
            "a test tried to POST to the Z.AI API; use the fake_llm fixture instead"
        )

    monkeypatch.setattr(llm, "_post", _refuse)
    # The client is cached for the process, so clear it before each test rather
    # than after: by teardown, _post itself may have been replaced by a fake
    # that never touches the cached client at all.
    llm.get_client.cache_clear()
    yield


@pytest.fixture(autouse=True)
def no_live_resend_call(monkeypatch):
    """Stop any test from actually emailing somebody."""

    def _refuse(*args, **kwargs):
        raise LiveApiCallAttempted(
            "a test tried to POST to Resend; use the fake_resend fixture instead"
        )

    monkeypatch.setattr(notify, "_post", _refuse)


@pytest.fixture
def fake_resend(monkeypatch):
    """Capture what would have been emailed, or make the send fail on demand.

    Returns the list the payloads land in, so a test can assert on the subject,
    recipient and body that Resend would have received.
    """

    def install(fail_with: Exception | None = None) -> list[dict]:
        sent: list[dict] = []

        def _capture(payload, timeout=15.0):
            sent.append(payload)
            if fail_with is not None:
                raise fail_with

        monkeypatch.setattr(notify, "_post", _capture)
        return sent

    return install


# --- Standing in for the Z.AI API -------------------------------------------


def zai_response(content: str, *, finish_reason: str = "stop", status: int = 200):
    """One chat-completions response, shaped the way Z.AI shapes them."""
    return httpx.Response(
        status,
        json={
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {"role": "assistant", "content": content},
                }
            ]
        },
        request=httpx.Request("POST", "https://api.z.ai/api/paas/v4/chat/completions"),
    )


def zai_error(status: int):
    """An error status with a body that echoes the request back.

    The echoed text is the point: several tests assert it does not survive into
    anything a visitor or a log reader can see.
    """
    return httpx.Response(
        status,
        json={"error": {"message": "invalid request: Northwind senior Flutter engineer"}},
        request=httpx.Request("POST", "https://api.z.ai/api/paas/v4/chat/completions"),
    )


@pytest.fixture
def fake_llm(monkeypatch):
    """Install a fake Z.AI transport and hand the test its call log.

    Pass one or more responses. Each call consumes the next; the last one
    repeats, so a single argument answers every call. An `Exception` is raised
    rather than returned, which is how transport failures are simulated.

    Usage:  calls = fake_llm(zai_response("An answer."))
            ...
            assert calls[0]["model"] == "glm-4.7-flash"
    """

    def install(*responses) -> list[dict]:
        calls: list[dict] = []
        queue = list(responses)

        def _capture(payload: dict, read_timeout: float = 0.0):
            calls.append(payload)
            item = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(item, Exception):
                raise item
            return item

        monkeypatch.setattr(llm, "_post", _capture)
        # Retry backoff is real seconds otherwise, and the retry path is
        # exercised by several tests.
        monkeypatch.setattr(llm, "_wait", lambda _seconds: None)
        return calls

    return install
