"""Contract tests against the real Z.AI API.

Excluded from the default run — `pytest.ini` sets `-m "not live"` — and opted
into with:

    pytest -m live

Two reasons they are not in the everyday suite. They need a key and a network,
and GLM-4.7-Flash permits exactly **one in-flight request per account**, so
running them alongside anything else on the same key makes both flaky for
reasons that have nothing to do with the code. They are written to run serially
and are deliberately few.

What they check is only what a mock cannot:

- the configured model ID is a model that exists
- the bearer token is accepted
- `response_format: json_object` is honoured
- `TriageResult`'s schema survives a round trip through a real model

What they deliberately do **not** check is the wording of anything generated.
A model is not deterministic; asserting on its prose produces a test that fails
on a Tuesday for no reason and teaches everyone to ignore red.
"""

from __future__ import annotations

import pytest

from app import llm, rag, triage
from app.schemas import ContactRequest, TriageResult

pytestmark = pytest.mark.live


SUBMISSION = ContactRequest(
    name="Dana Okafor",
    email="dana@example.com",
    message="We're hiring a senior Flutter engineer at Northwind and your XR work stood out.",
)


def test_the_configured_model_exists_and_the_key_is_accepted():
    """The single most valuable live check: a typo'd model ID or a bad key is
    invisible to every mocked test in the suite and fatal in production."""
    answer = llm.complete(
        "You are a test fixture. Answer with exactly one word.",
        "Reply with the word: ready",
        max_tokens=16,
    )
    assert answer, "the model returned nothing"


def test_json_mode_returns_parseable_json():
    """`response_format: json_object` is a documented guarantee. Verify it."""
    import json

    raw = llm.complete(
        'Reply with a JSON object having one key, "status", set to "ok".',
        "Go.",
        max_tokens=64,
        json_object=True,
    )
    assert isinstance(json.loads(raw), dict)


def test_triage_round_trips_its_schema_through_a_real_model():
    """The one thing the migration genuinely made weaker.

    The previous provider enforced the schema itself, so a mismatched shape was
    a state the API would not produce. Z.AI does not, so the schema lives in the
    prompt and is validated afterwards — which means "does a real model actually
    honour it?" is now an open question that only this test answers.
    """
    result = triage.triage(SUBMISSION)

    assert isinstance(result, TriageResult)
    # Shape and constraints only — never the wording.
    assert result.category in {
        "job_opportunity",
        "recruiter",
        "collaboration",
        "question",
        "spam",
        "other",
    }
    assert result.priority in {"high", "normal", "low"}
    assert result.summary.strip()
    assert result.draft_reply.strip()


def test_chat_generates_a_grounded_answer(monkeypatch):
    """End to end through the real prompt, with retrieval stubbed.

    Retrieval is stubbed rather than live because sqlite-vec has no wheel for
    the dev machine — the container suite covers the real thing.
    """
    from app.store import SearchResult

    monkeypatch.setattr(
        rag,
        "retrieve",
        lambda question, k=6: [
            SearchResult(
                source="experience.md",
                heading="Software Engineer at AI Talent",
                text="Ljuben Vassilev joined AI Talent in April 2026 as a Software Engineer.",
                distance=0.1,
            )
        ],
    )

    answer = rag.answer_question("Where does he work?")

    assert answer.text.strip()
    assert answer.sources
