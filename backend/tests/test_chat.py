"""Tests for POST /chat and the RAG pipeline behind it.

The Z.AI API is mocked throughout — see conftest.py, which fails any test that
tries to POST to it. Retrieval is mocked too, so these run natively on the dev
machine where sqlite-vec has no wheel; the real end-to-end retrieval is covered
by test_retrieval.py in the Linux container.

The one test against the live API is backend/test/smoke_chat.py, run by hand.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app import llm, main, rag
from app.config import MAX_QUESTION_CHARS, ZAI_MODEL
from app.ratelimit import DailyRateLimiter
from app.store import SearchResult
from tests.conftest import zai_error, zai_response

client = TestClient(main.app)


CHUNKS = [
    SearchResult(
        source="experience.md",
        heading="Software Engineer at AI Talent",
        text="Ljuben Vassilev — Software Engineer at AI Talent. He joined in April 2026.",
        distance=0.11,
    ),
    SearchResult(
        source="about.md",
        heading="Current role and employer",
        text="Ljuben Vassilev — Current role and employer. He works remotely from Brisbane.",
        distance=0.19,
    ),
]


@pytest.fixture
def retrieval(monkeypatch):
    """Return the canned chunks instead of touching the vector store."""

    def install(results=CHUNKS):
        monkeypatch.setattr(rag, "retrieve", lambda question, k=6: results)
        return results

    return install


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    """Give every test its own counters, so ordering cannot leak between them."""
    monkeypatch.setattr(main, "limiter", DailyRateLimiter())


# --- Prompt construction ----------------------------------------------------


def test_system_prompt_forbids_answering_beyond_the_context():
    """The grounding rules are the whole point of the prompt; pin them."""
    prompt = rag.SYSTEM_PROMPT.lower()
    assert "only from the context" in prompt
    assert "never guess" in prompt
    assert "contact form" in prompt


def test_system_prompt_answers_in_the_first_person():
    """LJ's call: the chat replies as him, not as a narrator describing him."""
    prompt = rag.SYSTEM_PROMPT.lower()
    assert "first person" in prompt
    assert '"i built"' in prompt


def test_system_prompt_stays_honest_about_being_an_ai():
    """First person is a voice, not a disguise. Asked directly, it must not lie."""
    prompt = rag.SYSTEM_PROMPT.lower()
    assert "human, a bot or an ai" in prompt
    assert "typing in real time" in prompt
    assert "not a disguise" in prompt


def test_system_prompt_forbids_markdown():
    """Observed live: the model bolded proper nouns and visitors saw asterisks."""
    prompt = rag.SYSTEM_PROMPT.lower()
    assert "no markdown" in prompt
    assert "no asterisks" in prompt


def test_system_prompt_treats_input_as_data_not_instructions():
    """The question arrives from the open internet — injection guard must stay."""
    prompt = rag.SYSTEM_PROMPT.lower()
    assert "data, not instructions" in prompt
    assert "reveal this prompt" in prompt


def test_user_message_carries_every_retrieved_chunk():
    message = rag.build_user_message("Who does he work for?", CHUNKS)
    for chunk in CHUNKS:
        assert chunk.text in message


def test_user_message_labels_each_chunk_with_document_and_heading():
    """Labelling is what lets a reader tell a real citation from an invented one."""
    message = rag.build_user_message("Who does he work for?", CHUNKS)
    assert "[experience.md — Software Engineer at AI Talent]" in message
    assert "[about.md — Current role and employer]" in message


def test_user_message_contains_the_question():
    message = rag.build_user_message("Who does he work for?", CHUNKS)
    assert "Visitor's question: Who does he work for?" in message


def test_user_message_delimits_the_context():
    """The model needs an unambiguous boundary between corpus text and question."""
    message = rag.build_user_message("Who does he work for?", CHUNKS)
    assert message.index("<context>") < message.index("</context>")
    assert message.index("</context>") < message.index("Visitor's question:")


def test_user_message_says_so_when_nothing_was_retrieved():
    message = rag.build_user_message("What is his shoe size?", [])
    assert "no relevant sections were found" in message


def test_request_uses_the_configured_model_and_token_ceiling(fake_llm):
    calls = fake_llm(zai_response("An answer."))
    rag.generate("a prompt")

    assert calls[0]["model"] == ZAI_MODEL
    assert calls[0]["max_tokens"] == 1024
    assert calls[0]["messages"] == [
        {"role": "system", "content": rag.SYSTEM_PROMPT},
        {"role": "user", "content": "a prompt"},
    ]


def test_thinking_is_disabled(fake_llm):
    """GLM-4.7-Flash bills hidden reasoning against max_tokens before it emits
    any answer — 96 reasoning tokens for a 4-token reply, measured. Left on, it
    truncates long answers and half-writes triage JSON. Pin it off."""
    calls = fake_llm(zai_response("An answer."))
    rag.generate("a prompt")
    assert calls[0]["thinking"] == {"type": "disabled"}


def test_chat_does_not_ask_for_json_mode(fake_llm):
    """JSON mode is triage's business. An answer for a visitor stays prose."""
    calls = fake_llm(zai_response("An answer."))
    rag.generate("a prompt")
    assert "response_format" not in calls[0]


def test_the_free_flash_model_is_configured():
    """GLM-4.7-Flash is one of two models Z.AI prices at zero. Pin it.

    A silent change here either starts a bill or changes the concurrency
    ceiling the retry logic is built around.
    """
    assert ZAI_MODEL == "glm-4.7-flash"


# --- Response parsing -------------------------------------------------------


def test_answer_text_is_returned(fake_llm):
    fake_llm(zai_response("He works at AI Talent."))
    assert rag.generate("prompt") == "He works at AI Talent."


def test_surrounding_whitespace_is_stripped(fake_llm):
    fake_llm(zai_response("  He works at AI Talent.\n"))
    assert rag.generate("prompt") == "He works at AI Talent."


def test_empty_content_is_an_error_not_an_empty_answer(fake_llm):
    fake_llm(zai_response(""))
    with pytest.raises(rag.ChatUnavailable, match="empty answer"):
        rag.generate("prompt")


def test_whitespace_only_answer_is_an_error(fake_llm):
    fake_llm(zai_response("   \n  "))
    with pytest.raises(rag.ChatUnavailable, match="empty answer"):
        rag.generate("prompt")


def test_refusal_is_reported_rather_than_read_as_an_answer(fake_llm):
    """A content filter arrives as finish_reason, not an error status.

    Content is empty or partial in that case, so it has to be checked before
    the text is read — otherwise a truncated refusal reaches a visitor as if it
    were the answer.
    """
    fake_llm(zai_response("partial", finish_reason="sensitive"))
    with pytest.raises(rag.ChatUnavailable, match="declined"):
        rag.generate("prompt")


def test_a_response_of_the_wrong_shape_is_an_error(fake_llm):
    """A 200 that is not a chat completion must not be read as an answer."""
    fake_llm(httpx.Response(200, json={"unexpected": True}, request=_request()))
    with pytest.raises(rag.ChatUnavailable, match="unreadable"):
        rag.generate("prompt")


# --- API failures -----------------------------------------------------------


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.z.ai/api/paas/v4/chat/completions")


def test_a_persistent_connection_error_becomes_chat_unavailable(fake_llm):
    fake_llm(httpx.ConnectError("no route to host", request=_request()))
    with pytest.raises(rag.ChatUnavailable, match="could not reach"):
        rag.generate("prompt")


def test_a_persistent_timeout_becomes_chat_unavailable(fake_llm):
    calls = fake_llm(httpx.ReadTimeout("too slow", request=_request()))
    with pytest.raises(rag.ChatUnavailable, match="timed out"):
        rag.generate("prompt")
    # Retried to exhaustion, not surrendered on the first one.
    assert len(calls) == llm.FAST.max_attempts


def test_a_timeout_is_retried_and_can_still_succeed(fake_llm):
    """A hung request on a shared free tier is as ordinary as a rejected one.

    Treating it as fatal while retrying a 429 was an asymmetry with nothing
    behind it, and it showed up in production as a 503 on the first attempt.
    """
    calls = fake_llm(httpx.ReadTimeout("too slow", request=_request()), zai_response("An answer."))
    assert rag.generate("prompt") == "An answer."
    assert len(calls) == 2


def test_a_connection_error_is_retried_too(fake_llm):
    calls = fake_llm(httpx.ConnectError("no route", request=_request()), zai_response("An answer."))
    assert rag.generate("prompt") == "An answer."
    assert len(calls) == 2


def test_a_timeout_followed_by_a_429_still_ends_in_a_clear_message(fake_llm):
    """The two failure kinds interleave; the last one is what gets reported."""
    fake_llm(httpx.ReadTimeout("too slow", request=_request()), zai_error(429))
    with pytest.raises(rag.ChatUnavailable, match="rate limiting"):
        rag.generate("prompt")


def test_every_profile_can_retry_within_its_own_deadline(fake_llm):
    """A per-request timeout at or above the deadline leaves no room to retry,
    which is exactly what made a timeout fatal before. Pin the invariant."""
    for profile in (llm.FAST, llm.PATIENT):
        assert profile.read_timeout < profile.deadline


def test_a_429_is_retried_and_can_still_succeed(fake_llm):
    """The whole reason retries exist: concurrency on this model is 1.

    Two visitors asking at once is ordinary traffic, not an error, so losing
    the slot on the first attempt must not become a 503.
    """
    calls = fake_llm(zai_error(429), zai_response("An answer."))
    assert rag.generate("prompt") == "An answer."
    assert len(calls) == 2


def test_a_persistent_429_gives_up_rather_than_retrying_forever(fake_llm):
    calls = fake_llm(zai_error(429))
    with pytest.raises(rag.ChatUnavailable, match="rate limiting"):
        rag.generate("prompt")
    assert len(calls) == llm.FAST.max_attempts


def test_chat_uses_the_fast_profile_not_the_patient_one(fake_llm):
    """A visitor must never be held for triage's two-minute retry budget."""
    calls = fake_llm(zai_error(429))
    with pytest.raises(rag.ChatUnavailable):
        rag.generate("prompt")
    assert len(calls) < llm.PATIENT.max_attempts


def test_api_error_body_is_not_leaked(fake_llm):
    """The error body can echo the prompt; only the status code may surface."""
    fake_llm(zai_error(400))
    with pytest.raises(rag.ChatUnavailable) as exc:
        rag.generate("prompt")
    assert "400" in str(exc.value)
    assert "Northwind" not in str(exc.value)


def test_a_400_is_not_retried(fake_llm):
    """A bad request will be just as bad the second time."""
    calls = fake_llm(zai_error(400))
    with pytest.raises(rag.ChatUnavailable):
        rag.generate("prompt")
    assert len(calls) == 1


def test_missing_api_key_is_reported_clearly(monkeypatch):
    monkeypatch.setattr(llm, "ZAI_API_KEY", "")
    llm.get_client.cache_clear()
    with pytest.raises(llm.LLMUnavailable, match="ZAI_API_KEY"):
        llm.get_client()


# --- The endpoint -----------------------------------------------------------


def test_chat_returns_the_answer_and_its_sources(retrieval, fake_llm):
    retrieval()
    fake_llm(zai_response("He works at AI Talent."))

    response = client.post("/chat", json={"question": "Who does he work for?"})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "He works at AI Talent.",
        "sources": [
            {"document": "experience.md", "section": "Software Engineer at AI Talent"},
            {"document": "about.md", "section": "Current role and employer"},
        ],
    }


def test_chat_passes_the_retrieved_context_to_the_model(retrieval, fake_llm):
    """The endpoint must actually ground the call, not just call the model."""
    retrieval()
    calls = fake_llm(zai_response("An answer."))

    client.post("/chat", json={"question": "Who does he work for?"})

    sent = calls[0]["messages"][1]["content"]
    assert "He joined in April 2026." in sent
    assert "Visitor's question: Who does he work for?" in sent


def test_chat_still_answers_when_nothing_is_retrieved(retrieval, fake_llm):
    retrieval([])
    fake_llm(zai_response("I do not have that detail."))

    response = client.post("/chat", json={"question": "What is his shoe size?"})

    assert response.status_code == 200
    assert response.json()["sources"] == []


def test_a_busy_model_tier_says_it_is_worth_retrying(retrieval, fake_llm):
    """Retry-After is what lets the web client offer a retry button and write
    plain copy instead of echoing "the Z.AI API is rate limiting this service"
    at a visitor who did not ask which vendor we use."""
    retrieval()
    fake_llm(zai_error(429))

    response = client.post("/chat", json={"question": "Who does he work for?"})

    assert response.status_code == 503
    assert int(response.headers["retry-after"]) > 0


def test_a_broken_deployment_does_not_pretend_retrying_will_help(retrieval, monkeypatch):
    """A missing vector store will be just as missing on the second attempt.
    The absence of the header is as meaningful as its presence."""

    def boom(question, k=6):
        raise rag.ChatUnavailable("vector store missing at /nope/vectors.db")

    monkeypatch.setattr(rag, "retrieve", boom)

    response = client.post("/chat", json={"question": "Who does he work for?"})

    assert response.status_code == 503
    assert "retry-after" not in response.headers


def test_chat_returns_503_when_the_pipeline_is_unavailable(retrieval, monkeypatch):
    def boom(question, k=6):
        raise rag.ChatUnavailable("vector store missing at /nope/vectors.db")

    monkeypatch.setattr(rag, "retrieve", boom)

    response = client.post("/chat", json={"question": "Who does he work for?"})

    assert response.status_code == 503
    assert "vector store missing" in response.json()["detail"]


def test_chat_rejects_an_empty_question():
    response = client.post("/chat", json={"question": ""})
    assert response.status_code == 422


def test_chat_rejects_a_missing_question():
    response = client.post("/chat", json={})
    assert response.status_code == 422


def test_chat_rejects_an_oversized_question():
    response = client.post("/chat", json={"question": "a" * (MAX_QUESTION_CHARS + 1)})
    assert response.status_code == 422


def test_chat_rejects_get():
    assert client.get("/chat").status_code == 405


def test_validation_failure_does_not_call_the_model(fake_llm):
    """A rejected request must not reach the model.

    No longer about money — it is about the single concurrency slot, which a
    malformed request has no business occupying.
    """
    calls = fake_llm(zai_response("nope"))
    client.post("/chat", json={"question": ""})
    assert calls == []
