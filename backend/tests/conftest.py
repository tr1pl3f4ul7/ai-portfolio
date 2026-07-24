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

from dataclasses import dataclass, field

import pytest

from app import config, notify, rag


class LiveApiCallAttempted(AssertionError):
    """Raised if a test tries to reach the real Anthropic API or Resend."""


# Obvious on sight, and obviously not a credential, if one ever surfaces in
# output. Must still look like a key so that "is it set?" checks behave.
DUMMY_ANTHROPIC_KEY = "sk-ant-api03-TEST-KEY-NOT-REAL"
DUMMY_RESEND_KEY = "re_TEST_KEY_NOT_REAL"


@pytest.fixture(autouse=True)
def no_real_credentials(monkeypatch):
    """Keep the real keys out of the test process entirely.

    config.py loads backend/.env, so without this the genuine keys are in scope
    for every test — and a failing assertion renders the locals of the frame it
    failed in. That is exactly how a key ends up in a terminal, a CI log or a
    pasted stack trace. The guards below stop a call going *out*; this stops a
    credential being in memory to leak in the first place.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", DUMMY_ANTHROPIC_KEY)
    monkeypatch.setenv("RESEND_API_KEY", DUMMY_RESEND_KEY)
    # config's module-level reads already happened at import, so patch the
    # bound values too — including rag's, which imported its own copy.
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", DUMMY_ANTHROPIC_KEY)
    monkeypatch.setattr(config, "RESEND_API_KEY", DUMMY_RESEND_KEY)
    monkeypatch.setattr(rag, "ANTHROPIC_API_KEY", DUMMY_ANTHROPIC_KEY)
    monkeypatch.setattr(notify, "RESEND_API_KEY", DUMMY_RESEND_KEY)
    monkeypatch.setattr(notify, "CONTACT_NOTIFY_TO", "nobody@example.com")


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
