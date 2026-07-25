"""Tests for POST /chat and the RAG pipeline behind it.

The Claude API is mocked throughout — see conftest.py, which fails any test that
tries to construct a real client. Retrieval is mocked too, so these run natively
on the dev machine where sqlite-vec has no wheel; the real end-to-end retrieval
is covered by test_retrieval.py in the Linux container.

The one test against the live API is backend/test/smoke_chat.py, run by hand.
"""

from __future__ import annotations

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, rag
from app.config import ANTHROPIC_MODEL, MAX_QUESTION_CHARS
from app.ratelimit import DailyRateLimiter
from app.store import SearchResult
from tests.conftest import FakeMessage, FakeTextBlock

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


def test_request_uses_the_configured_model_and_token_ceiling(fake_claude):
    fake = fake_claude(FakeMessage(content=[FakeTextBlock("An answer.")]))
    rag.generate("a prompt")

    call = fake.messages.calls[0]
    assert call["model"] == ANTHROPIC_MODEL
    assert call["max_tokens"] == 1024
    assert call["system"] == rag.SYSTEM_PROMPT
    assert call["messages"] == [{"role": "user", "content": "a prompt"}]


def test_haiku_is_the_configured_model():
    """LJ chose Haiku for /chat. A silent change here changes the bill."""
    assert ANTHROPIC_MODEL == "claude-haiku-4-5"


# --- Response parsing -------------------------------------------------------


def test_answer_text_is_extracted_from_the_content_blocks(fake_claude):
    fake_claude(FakeMessage(content=[FakeTextBlock("He works at AI Talent.")]))
    assert rag.generate("prompt") == "He works at AI Talent."


def test_multiple_text_blocks_are_joined(fake_claude):
    fake_claude(FakeMessage(content=[FakeTextBlock("One. "), FakeTextBlock("Two.")]))
    assert rag.generate("prompt") == "One. Two."


def test_non_text_blocks_are_ignored(fake_claude):
    """Content is a union; anything that is not a text block must not crash us."""

    class OtherBlock:
        type = "thinking"

    fake_claude(FakeMessage(content=[OtherBlock(), FakeTextBlock("Answer.")]))
    assert rag.generate("prompt") == "Answer."


def test_empty_content_is_an_error_not_an_empty_answer(fake_claude):
    fake_claude(FakeMessage(content=[]))
    with pytest.raises(rag.ChatUnavailable, match="empty answer"):
        rag.generate("prompt")


def test_whitespace_only_answer_is_an_error(fake_claude):
    fake_claude(FakeMessage(content=[FakeTextBlock("   \n  ")]))
    with pytest.raises(rag.ChatUnavailable, match="empty answer"):
        rag.generate("prompt")


def test_refusal_is_reported_rather_than_read_as_an_answer(fake_claude):
    """stop_reason=refusal leaves content empty or partial — check it first."""
    fake_claude(FakeMessage(content=[FakeTextBlock("partial")], stop_reason="refusal"))
    with pytest.raises(rag.ChatUnavailable, match="declined"):
        rag.generate("prompt")


# --- API failures -----------------------------------------------------------


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def test_connection_error_becomes_chat_unavailable(fake_claude):
    fake_claude(anthropic.APIConnectionError(request=_request()))
    with pytest.raises(rag.ChatUnavailable, match="could not reach"):
        rag.generate("prompt")


def test_rate_limit_from_the_api_becomes_chat_unavailable(fake_claude):
    response = httpx.Response(429, request=_request())
    fake_claude(anthropic.RateLimitError("slow down", response=response, body=None))
    with pytest.raises(rag.ChatUnavailable, match="rate limiting"):
        rag.generate("prompt")


def test_api_error_body_is_not_leaked(fake_claude):
    """The error body can echo the prompt; only the status code may surface."""
    response = httpx.Response(400, request=_request())
    fake_claude(
        anthropic.BadRequestError("secret prompt echoed back", response=response, body=None)
    )
    with pytest.raises(rag.ChatUnavailable) as exc:
        rag.generate("prompt")
    assert "400" in str(exc.value)
    assert "secret prompt echoed back" not in str(exc.value)


def test_missing_api_key_is_reported_clearly(monkeypatch):
    monkeypatch.setattr(rag, "ANTHROPIC_API_KEY", "")
    rag.get_client.cache_clear()
    with pytest.raises(rag.ChatUnavailable, match="ANTHROPIC_API_KEY"):
        rag.get_client()


# --- The endpoint -----------------------------------------------------------


def test_chat_returns_the_answer_and_its_sources(retrieval, fake_claude):
    retrieval()
    fake_claude(FakeMessage(content=[FakeTextBlock("He works at AI Talent.")]))

    response = client.post("/chat", json={"question": "Who does he work for?"})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "He works at AI Talent.",
        "sources": [
            {"document": "experience.md", "section": "Software Engineer at AI Talent"},
            {"document": "about.md", "section": "Current role and employer"},
        ],
    }


def test_chat_passes_the_retrieved_context_to_claude(retrieval, fake_claude):
    """The endpoint must actually ground the call, not just call the model."""
    retrieval()
    fake = fake_claude(FakeMessage(content=[FakeTextBlock("An answer.")]))

    client.post("/chat", json={"question": "Who does he work for?"})

    sent = fake.messages.calls[0]["messages"][0]["content"]
    assert "He joined in April 2026." in sent
    assert "Visitor's question: Who does he work for?" in sent


def test_chat_still_answers_when_nothing_is_retrieved(retrieval, fake_claude):
    retrieval([])
    fake_claude(FakeMessage(content=[FakeTextBlock("I do not have that detail.")]))

    response = client.post("/chat", json={"question": "What is his shoe size?"})

    assert response.status_code == 200
    assert response.json()["sources"] == []


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


def test_validation_failure_does_not_call_claude(fake_claude):
    """A rejected request must cost nothing."""
    fake = fake_claude(FakeMessage(content=[FakeTextBlock("nope")]))
    client.post("/chat", json={"question": ""})
    assert fake.messages.calls == []
