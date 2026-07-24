"""Tests for contact-form triage.

The Claude call is mocked throughout — conftest fails any test that reaches the
real API. What these cover is the prompt, the failure paths, and the schema
contract.

A note on what is *not* testable here: whether the API accepts the JSON schema
`messages.parse` derives from `TriageResult`. That is only proven by a live
call, which is what backend/test/smoke_contact.py is for.
"""

from __future__ import annotations

import anthropic
import httpx
import pytest

from app import triage
from app.config import TRIAGE_MODEL
from app.schemas import ContactRequest, TriageResult
from tests.conftest import FakeParsedMessage

SUBMISSION = ContactRequest(
    name="Dana Okafor",
    email="dana@example.com",
    message="We're hiring a senior Flutter engineer at Northwind and your XR work stood out.",
)

RESULT = TriageResult(
    category="job_opportunity",
    priority="high",
    summary="Northwind is hiring a senior Flutter engineer and approached him directly.",
    draft_reply="Thanks for getting in touch — I'd be glad to hear more. I'll follow up shortly.",
    company="Northwind",
    role="Senior Flutter Engineer",
)


# --- The prompt -------------------------------------------------------------


def test_system_prompt_says_the_output_is_for_lj_not_the_sender():
    prompt = triage.SYSTEM_PROMPT.lower()
    assert "never for the sender" in prompt


def test_system_prompt_treats_the_submission_as_data():
    """This message is the most untrusted input the backend accepts."""
    prompt = triage.SYSTEM_PROMPT.lower()
    assert "data, not instructions" in prompt
    assert "spam signal" in prompt


def test_system_prompt_forbids_promising_anything():
    """The draft goes out under LJ's name. It must not commit him to anything."""
    prompt = triage.SYSTEM_PROMPT.lower()
    assert "never sent" in prompt
    assert "no rates" in prompt
    assert "do not promise" in prompt


def test_system_prompt_forbids_inventing_details():
    assert "never invent" in triage.SYSTEM_PROMPT.lower()
    assert "email domain" in triage.SYSTEM_PROMPT.lower()


def test_user_message_carries_every_field():
    message = triage.build_user_message(SUBMISSION)
    assert "Dana Okafor" in message
    assert "dana@example.com" in message
    assert "senior Flutter engineer at Northwind" in message


def test_user_message_delimits_the_submission():
    """Its bounds must be unambiguous, since a sender may try to fake an end."""
    message = triage.build_user_message(SUBMISSION)
    assert message.startswith("<submission>")
    assert message.endswith("</submission>")


def test_request_uses_the_configured_model_and_schema(fake_claude):
    fake = fake_claude(FakeParsedMessage(parsed_output=RESULT))
    triage.triage(SUBMISSION)

    call = fake.messages.calls[0]
    assert call["model"] == TRIAGE_MODEL
    assert call["system"] == triage.SYSTEM_PROMPT
    assert call["output_format"] is TriageResult


def test_triage_returns_the_parsed_result(fake_claude):
    fake_claude(FakeParsedMessage(parsed_output=RESULT))
    assert triage.triage(SUBMISSION) == RESULT


# --- Failure paths ----------------------------------------------------------


def test_unparseable_response_is_a_failure_not_a_default(fake_claude):
    """A None parsed_output means the schema contract was not met. Say so."""
    fake_claude(FakeParsedMessage(parsed_output=None))
    with pytest.raises(triage.TriageUnavailable, match="no parseable triage result"):
        triage.triage(SUBMISSION)


def test_refusal_is_reported(fake_claude):
    fake_claude(FakeParsedMessage(parsed_output=RESULT, stop_reason="refusal"))
    with pytest.raises(triage.TriageUnavailable, match="declined"):
        triage.triage(SUBMISSION)


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def test_connection_error_becomes_triage_unavailable(fake_claude):
    fake_claude(anthropic.APIConnectionError(request=_request()))
    with pytest.raises(triage.TriageUnavailable, match="could not reach"):
        triage.triage(SUBMISSION)


def test_rate_limit_becomes_triage_unavailable(fake_claude):
    response = httpx.Response(429, request=_request())
    fake_claude(anthropic.RateLimitError("slow down", response=response, body=None))
    with pytest.raises(triage.TriageUnavailable, match="rate limiting"):
        triage.triage(SUBMISSION)


def test_api_error_does_not_leak_the_submission_back(fake_claude):
    """The error body can echo the message — a stranger's text. Keep the status."""
    response = httpx.Response(400, request=_request())
    fake_claude(
        anthropic.BadRequestError(
            "invalid_request: We're hiring a senior Flutter engineer at Northwind",
            response=response,
            body=None,
        )
    )
    with pytest.raises(triage.TriageUnavailable) as exc:
        triage.triage(SUBMISSION)
    assert "400" in str(exc.value)
    assert "Northwind" not in str(exc.value)


# --- The schema itself ------------------------------------------------------


def test_optional_fields_default_to_none():
    """A sender who names no company must not produce an invented one."""
    minimal = TriageResult(
        category="question",
        priority="normal",
        summary="Asked which VR headsets he has shipped on.",
        draft_reply="Thanks for asking — I'll come back to you with detail.",
    )
    assert minimal.company is None
    assert minimal.role is None


def test_category_is_constrained():
    with pytest.raises(ValueError):
        TriageResult(
            category="definitely_hire_this_person",
            priority="high",
            summary="x",
            draft_reply="y",
        )


def test_priority_is_constrained():
    with pytest.raises(ValueError):
        TriageResult(category="question", priority="URGENT!!!", summary="x", draft_reply="y")
