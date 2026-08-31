"""Tests for the test suite's own safety guards.

These exist because of a real incident during Step 2.4. A test reached the
model client unmocked, the live-call guard correctly refused — and pytest,
rendering the locals of the frame that raised, printed the genuine API key into
the terminal. The outbound call was blocked; the credential still leaked,
because it was in memory to be leaked.

So there are two independent properties now, and both are worth pinning:

1. No real credential is ever in scope during a test.
2. No call ever goes out to Z.AI or Resend.

Still worth having now that inference is free: a leaked key is a leaked key
whether or not it has a bill attached, and Resend can still email a real person.

A guard nobody tests is a guard that quietly stops working.
"""

from __future__ import annotations

import pytest

from app import config, llm, notify, observability
from tests.conftest import DUMMY_RESEND_KEY, DUMMY_ZAI_KEY, LiveApiCallAttempted

# --- 1. No real credentials in scope ----------------------------------------


def test_the_zai_key_in_scope_is_the_dummy():
    assert llm.ZAI_API_KEY == DUMMY_ZAI_KEY
    assert config.ZAI_API_KEY == DUMMY_ZAI_KEY


def test_the_resend_key_in_scope_is_the_dummy():
    assert notify.RESEND_API_KEY == DUMMY_RESEND_KEY
    assert config.RESEND_API_KEY == DUMMY_RESEND_KEY


def test_the_environment_carries_the_dummy_too(monkeypatch):
    """Anything reading os.environ directly must also get the fake."""
    import os

    assert os.environ["ZAI_API_KEY"] == DUMMY_ZAI_KEY
    assert os.environ["RESEND_API_KEY"] == DUMMY_RESEND_KEY


def test_the_dummies_are_unmistakably_not_credentials():
    """If one ever does surface in output, nobody should have to wonder."""
    for dummy in (DUMMY_ZAI_KEY, DUMMY_RESEND_KEY):
        assert "TEST" in dummy and "NOT" in dummy and "REAL" in dummy


def test_the_notification_recipient_is_not_a_real_address():
    assert notify.CONTACT_NOTIFY_TO.endswith("@example.com")


def test_sentry_is_disabled_during_tests():
    """Observed: the suite was posting test exceptions to the live project.

    init_sentry() runs at import time, so an empty DSN has to be in the
    environment before `app` is imported at all — see the module-level block in
    conftest, which no fixture can substitute for.
    """
    import os

    assert os.environ["SENTRY_DSN"] == ""
    assert config.SENTRY_DSN == ""
    assert observability.SENTRY_DSN == ""
    assert observability.init_sentry() is False


# --- 2. No calls go out -----------------------------------------------------


def test_posting_to_the_zai_api_is_refused():
    with pytest.raises(LiveApiCallAttempted, match="POST to the Z.AI API"):
        llm._post({"model": "glm-4.7-flash"})


def test_posting_to_resend_is_refused():
    with pytest.raises(LiveApiCallAttempted, match="POST to Resend"):
        notify._post({"to": ["someone@example.com"]})


def test_the_refusal_names_the_way_out():
    """A guard that fires without saying what to do instead just wastes time."""
    with pytest.raises(LiveApiCallAttempted, match="fake_llm fixture"):
        llm._post({})
    with pytest.raises(LiveApiCallAttempted, match="fake_resend fixture"):
        notify._post({})
