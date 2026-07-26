"""Shared test fixtures, and the guards that keep the suite offline.

Two autouse guards apply to every test in this directory:

- `no_live_anthropic_client` replaces `anthropic.Anthropic` with a class that
  refuses to be constructed.
- `no_live_resend_call` replaces the raw POST inside `app.notify` with one that
  refuses to run.

Between them, any code path that would reach the network fails loudly with a
clear message instead of quietly spending money or emailing a real person — the
CLAUDE.md rule made mechanical rather than remembered.

Tests that need either patch `rag.get_client` or use `fake_resend`; neither
goes near the replaced functions.
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
DUMMY_ANTHROPIC_KEY = "sk-ant-api03-TEST-KEY-NOT-REAL"
DUMMY_RESEND_KEY = "re_TEST_KEY_NOT_REAL"

os.environ["ANTHROPIC_API_KEY"] = DUMMY_ANTHROPIC_KEY
os.environ["RESEND_API_KEY"] = DUMMY_RESEND_KEY
os.environ["CONTACT_NOTIFY_TO"] = "nobody@example.com"
os.environ["SENTRY_DSN"] = ""

from dataclasses import dataclass, field

import pytest

from app import config, notify, observability, rag


class LiveApiCallAttempted(AssertionError):
    """Raised if a test tries to reach the real Anthropic API or Resend."""


@pytest.fixture(autouse=True)
def no_real_credentials(monkeypatch):
    """Belt to the module-level braces above.

    The environment is already clean by the time this runs; what this covers is
    the *bound copies* — modules that did `from app.config import X` hold their
    own reference, so patching the environment alone would not reach them.

    Why both layers: a failing assertion renders the locals of the frame it
    failed in, which is exactly how a real key reached a terminal once already.
    Removing the credential from the process beats intercepting its use.
    """
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", DUMMY_ANTHROPIC_KEY)
    monkeypatch.setattr(config, "RESEND_API_KEY", DUMMY_RESEND_KEY)
    monkeypatch.setattr(config, "SENTRY_DSN", "")
    monkeypatch.setattr(rag, "ANTHROPIC_API_KEY", DUMMY_ANTHROPIC_KEY)
    monkeypatch.setattr(notify, "RESEND_API_KEY", DUMMY_RESEND_KEY)
    monkeypatch.setattr(notify, "CONTACT_NOTIFY_TO", "nobody@example.com")
    monkeypatch.setattr(observability, "SENTRY_DSN", "")


@pytest.fixture(autouse=True)
def no_live_anthropic_client(monkeypatch):
    import anthropic

    def _refuse(*args, **kwargs):
        raise LiveApiCallAttempted(
            "a test tried to construct a real Anthropic client; "
            "patch rag.get_client instead"
        )

    monkeypatch.setattr(anthropic, "Anthropic", _refuse)
    # The client is cached for the process, so clear it before each test rather
    # than after: by teardown, get_client itself may have been monkeypatched to
    # a fake with no cache to clear.
    rag.get_client.cache_clear()
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


# --- Fakes standing in for the Anthropic SDK's response objects -------------


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeMessage:
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"


@dataclass
class FakeParsedMessage:
    """What `messages.parse` returns: a validated object, or None if it failed."""

    parsed_output: object = None
    stop_reason: str = "end_turn"


class FakeMessages:
    """Records the calls it receives so tests can assert on the prompt.

    `create` and `parse` share one response and one call log — no test uses both
    in a single call, and keeping them together means a fake cannot silently
    answer the wrong one.
    """

    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def _record(self, kwargs):
        self.calls.append(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    def create(self, **kwargs):
        return self._record(kwargs)

    def parse(self, **kwargs):
        return self._record(kwargs)


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)


@pytest.fixture
def fake_claude(monkeypatch):
    """Install a fake Claude client and hand the test its call log.

    Usage:  client = fake_claude(FakeMessage(content=[FakeTextBlock("hi")]))
            ...
            assert client.messages.calls[0]["model"] == ...
    """

    def install(response) -> FakeClient:
        client = FakeClient(response)
        monkeypatch.setattr(rag, "get_client", lambda: client)
        return client

    return install
