"""Request and response models.

These are the API contract. The web chat widget and the Cloudflare Worker
both read these shapes, so a change here is a change to two clients — see
the `api-contract` skill before editing.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.config import MAX_MESSAGE_CHARS, MAX_NAME_CHARS, MAX_QUESTION_CHARS


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


class ContactRequest(BaseModel):
    """A contact-form submission.

    Every field here is written by a stranger on the open internet. It is the
    most untrusted input the backend accepts — it reaches a model, and the
    model's output is drafted for LJ to send. Length limits are the first line
    of defence; the triage prompt is the second.
    """

    name: str = Field(min_length=1, max_length=MAX_NAME_CHARS)
    email: EmailStr = Field(description="Where LJ would reply.")
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ContactResponse(BaseModel):
    """Acknowledgement returned to the sender.

    Deliberately says nothing about the triage. The classification, priority and
    draft reply are written for LJ; telling a sender they were filed as
    low-priority spam would be a remarkable own goal. The reference is here so a
    follow-up email can quote it.
    """

    received: bool
    reference: str


class TriageResult(BaseModel):
    """What the model returns for a submission.

    `model_json_schema()` of this class is written verbatim into the triage
    system prompt, so the field names and descriptions below are literally part
    of the prompt — the model reads them. Z.AI guarantees valid JSON but not
    conformance to a schema, so this class is also what validates the reply.
    Never returned to the sender.
    """

    category: Literal[
        "job_opportunity",
        "recruiter",
        "collaboration",
        "question",
        "spam",
        "other",
    ]
    priority: Literal["high", "normal", "low"]
    summary: str = Field(description="One or two sentences telling LJ what this is.")
    draft_reply: str = Field(description="A reply LJ could edit and send. Never sent automatically.")
    company: str | None = Field(
        default=None, description="Company the sender named, or null if none was given."
    )
    role: str | None = Field(
        default=None, description="Role or job title mentioned, or null if none was given."
    )


class ErrorResponse(BaseModel):
    """Body returned with every non-2xx response from this API."""

    detail: str


# --- Content -----------------------------------------------------------------
#
# Portfolio copy, served so it can be edited once (a JSON file, a commit, a
# backend deploy) without a web rebuild. Source files live in data/content/ —
# see app/content.py.


class ProfileContent(BaseModel):
    """Hero copy — the web hero."""

    name: str
    location: str
    tagline: str


class SectionContent(BaseModel):
    """The label/heading/description shape several sections share."""

    label: str
    heading: str
    description: str


class BrowserContent(SectionContent):
    """Web's on-device project-finder section copy."""


class AskContent(SectionContent):
    """Chat section copy."""

    suggestions: list[str]


class ContactContent(SectionContent):
    """Contact section copy."""


class ProjectItem(BaseModel):
    """One project card."""

    company: str
    year: str
    name: str
    note: str


class ProjectsContent(BaseModel):
    """The project cards.

    Shared by web's "selected work" grid and web's on-device finder (which
    matches against these as its corpus — decision 44).
    """

    label: str
    heading: str
    items: list[ProjectItem]
