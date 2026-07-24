"""Shared test fixtures, and the guard that keeps the suite offline.

`no_live_anthropic_client` is autouse and applies to every test in this
directory. It replaces `anthropic.Anthropic` with a class that refuses to be
constructed, so any code path that would reach the real API fails loudly with a
clear message instead of quietly spending money — the CLAUDE.md rule made
mechanical rather than remembered.

Tests that need a client patch `rag.get_client` to return a fake, which never
touches the replaced class.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app import rag


class LiveApiCallAttempted(AssertionError):
    """Raised if a test tries to build a real Anthropic client."""


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


# --- Fakes standing in for the Anthropic SDK's response objects -------------


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeMessage:
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"


class FakeMessages:
    """Records the single call it receives so tests can assert on the prompt."""

    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


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
