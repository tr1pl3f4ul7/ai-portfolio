"""Tests for contact-form triage.

The model call is mocked throughout — conftest fails any test that reaches the
real API. What these cover is the prompt, the failure paths, and the schema
contract.

A note on what is *not* testable here: whether a real model, given this schema
in its prompt, actually returns JSON that validates. Z.AI guarantees syntactic
validity but not conformance, so that is proven by a live call — see the `live`
marker in CLAUDE.md and backend/test/smoke_contact.py.
"""

from __future__ import annotations

import httpx
import pytest

from app import llm, triage
from app.config import TRIAGE_MAX_TOKENS, ZAI_MODEL
from app.schemas import ContactRequest, TriageResult
from tests.conftest import zai_error, zai_response

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


def test_request_uses_the_configured_model_and_asks_for_json(fake_llm):
    calls = fake_llm(zai_response(RESULT.model_dump_json()))
    triage.triage(SUBMISSION)

    assert calls[0]["model"] == ZAI_MODEL
    assert calls[0]["max_tokens"] == TRIAGE_MAX_TOKENS
    assert calls[0]["messages"][0] == {"role": "system", "content": triage.SYSTEM_PROMPT}
    assert calls[0]["response_format"] == {"type": "json_object"}


def test_the_schema_is_carried_in_the_prompt():
    """Z.AI enforces no schema, so the prompt is where the contract lives.

    If this ever stops being true the model is being asked for JSON with no
    statement of what shape it should take, and validation would reject
    everything it returned.
    """
    prompt = triage.SYSTEM_PROMPT
    for field in ("category", "priority", "summary", "draft_reply", "company", "role"):
        assert f'"{field}"' in prompt
    assert "job_opportunity" in prompt
    assert "JSON Schema" in prompt


def test_triage_returns_the_validated_result(fake_llm):
    fake_llm(zai_response(RESULT.model_dump_json()))
    assert triage.triage(SUBMISSION) == RESULT


# --- Failure paths ----------------------------------------------------------


def test_malformed_json_is_a_failure_not_a_default(fake_llm):
    fake_llm(zai_response("not json at all"))
    with pytest.raises(triage.TriageUnavailable, match="no parseable triage result"):
        triage.triage(SUBMISSION)


def test_json_of_the_wrong_shape_is_a_failure(fake_llm):
    """Valid JSON that is not a TriageResult. Exactly what json_object allows."""
    fake_llm(zai_response('{"category": "definitely_hire_him", "priority": "URGENT"}'))
    with pytest.raises(triage.TriageUnavailable, match="no parseable triage result"):
        triage.triage(SUBMISSION)


def test_a_validation_failure_does_not_carry_the_submission_into_the_traceback(fake_llm):
    """A pydantic ValidationError quotes its input, and that input derives from
    a stranger's message. It must not be chained onto what we raise."""
    fake_llm(zai_response('{"summary": "We are hiring at Northwind"}'))
    with pytest.raises(triage.TriageUnavailable) as exc:
        triage.triage(SUBMISSION)
    assert exc.value.__cause__ is None
    assert "Northwind" not in str(exc.value)


def test_refusal_is_reported(fake_llm):
    fake_llm(zai_response("", finish_reason="sensitive"))
    with pytest.raises(triage.TriageUnavailable, match="declined"):
        triage.triage(SUBMISSION)


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.z.ai/api/paas/v4/chat/completions")


def test_connection_error_becomes_triage_unavailable(fake_llm):
    fake_llm(httpx.ConnectError("no route to host", request=_request()))
    with pytest.raises(triage.TriageUnavailable, match="could not reach"):
        triage.triage(SUBMISSION)


def test_rate_limit_becomes_triage_unavailable(fake_llm):
    fake_llm(zai_error(429))
    with pytest.raises(triage.TriageUnavailable, match="rate limiting"):
        triage.triage(SUBMISSION)


def test_triage_retries_far_harder_than_chat_does(fake_llm):
    """Triage runs unwatched in a background task, which is the whole reason it
    can afford a budget that would be unacceptable in front of a visitor."""
    calls = fake_llm(zai_error(429))
    with pytest.raises(triage.TriageUnavailable):
        triage.triage(SUBMISSION)
    assert len(calls) == llm.PATIENT.max_attempts
    assert llm.PATIENT.max_attempts > llm.FAST.max_attempts


def test_api_error_does_not_leak_the_submission_back(fake_llm):
    """The error body can echo the message — a stranger's text. Keep the status."""
    fake_llm(zai_error(400))
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
