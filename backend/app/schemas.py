"""Request and response models.

These are the API contract. The web chat widget, the Flutter app and the
Cloudflare Worker all read these shapes, so a change here is a change to three
clients — see the `api-contract` skill before editing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import MAX_QUESTION_CHARS


class ChatRequest(BaseModel):
    """A visitor's question."""

    question: str = Field(
        min_length=1,
        max_length=MAX_QUESTION_CHARS,
        description="The visitor's question about LJ's work and experience.",
    )


class Source(BaseModel):
    """One retrieved chunk, identified well enough for a client to cite it."""

    document: str = Field(description="Corpus file the section came from, e.g. 'experience.md'.")
    section: str = Field(description="Heading of the section within that file.")


class ChatResponse(BaseModel):
    """A grounded answer plus what it was grounded in.

    `sources` is what makes the answer auditable: a visitor — or LJ reading the
    logs — can see exactly which sections of the corpus were in front of the
    model. An answer with an empty `sources` list was generated from nothing
    retrieved, which is worth surfacing rather than hiding.
    """

    answer: str
    sources: list[Source]


class ErrorResponse(BaseModel):
    """Body returned with every non-2xx response from this API."""

    detail: str
