"""FastAPI application for the AI portfolio backend.

Exposes the health check and the RAG chatbot. Contact triage (/contact) arrives
in Step 2.4.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from app import notify, observability, rag, ratelimit, submissions, triage
from app.config import CONTACT_DAILY_LIMIT_PER_IP, CONTACT_DAILY_LIMIT_TOTAL
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ContactRequest,
    ContactResponse,
    ErrorResponse,
    Source,
)

# Before the app is constructed: Sentry's ASGI integration wraps the app at
# init time, so initialising it after would leave requests untraced. A no-op
# unless SENTRY_DSN is set, which it is not locally or in tests.
observability.init_sentry()

limiter = ratelimit.DailyRateLimiter()

# Separate counters, deliberately. Chat traffic must not be able to exhaust the
# contact form — being unable to receive an opportunity is a worse outcome than
# being unable to answer a question about one.
contact_limiter = ratelimit.DailyRateLimiter(
    per_ip_limit=CONTACT_DAILY_LIMIT_PER_IP,
    total_limit=CONTACT_DAILY_LIMIT_TOTAL,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the embedding model before the first request rather than during it.

    It is roughly 90 MB and takes a couple of seconds to load, which a visitor
    should not pay for. Failure is logged and swallowed on purpose: if the model
    or the vector store is broken, /chat says so with a 503 while /health stays
    green for the uptime monitor. A backend that cannot answer questions is
    still a backend that should report its own state honestly.
    """
    try:
        from app.embeddings import get_model

        get_model()
    except Exception as exc:  # noqa: BLE001 - startup must not be fatal
        print(f"warning: embedding model failed to load at startup: {exc}")
    yield


app = FastAPI(
    title="AI Portfolio API",
    description="RAG chatbot and contact triage for the AI showcase portfolio.",
    version="0.2.0",
    lifespan=lifespan,
)


class HealthResponse(BaseModel):
    """Response body for the health check."""

    status: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report that the process is up.

    Deliberately dependency-free: no Claude call, no vector store, no disk I/O.
    An external uptime monitor and every post-deploy smoke test gate on this
    endpoint, so it must stay fast and must not fail because something
    downstream is unhealthy. Checks for those dependencies belong in a separate
    readiness endpoint if they are ever needed.
    """
    return HealthResponse(status="ok")


@app.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        429: {"model": ErrorResponse, "description": "Daily request limit reached"},
        503: {"model": ErrorResponse, "description": "Retrieval or the Claude API is unavailable"},
    },
)
def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """Answer a visitor's question from the corpus.

    Rate limiting comes first: an over-limit request must not reach the Claude
    API, since spending money on it is the thing the limit exists to prevent.
    """
    try:
        limiter.check_and_count(ratelimit.client_ip(request))
    except ratelimit.RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

    try:
        answer = rag.answer_question(payload.question)
    except rag.ChatUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ChatResponse(
        answer=answer.text,
        sources=[Source(document=r.source, section=r.heading) for r in answer.sources],
    )


@app.post(
    "/contact",
    response_model=ContactResponse,
    responses={
        429: {"model": ErrorResponse, "description": "Daily submission limit reached"},
        503: {"model": ErrorResponse, "description": "The submission could not be stored"},
    },
)
def contact(payload: ContactRequest, request: Request) -> ContactResponse:
    """Accept a contact submission, triage it, and tell LJ about it.

    The order matters more than anything else here. The message is written to
    the store **first**, before any network call, so that neither Claude being
    down nor Resend being down can lose it. Both of those steps are then
    best-effort: they log and continue rather than failing the request, because
    a visitor who typed out a real enquiry should not be told to try again over
    something that already succeeded from their side.

    Only a failure to store is fatal — at that point there is genuinely nothing
    holding their message, and saying so honestly beats a 200 that means nothing.
    """
    try:
        contact_limiter.check_and_count(ratelimit.client_ip(request))
    except ratelimit.RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

    try:
        reference = submissions.record(payload)
    except Exception as exc:  # Catching broadly here is deliberate — the one failure worth surfacing
        raise HTTPException(status_code=503, detail="could not store the submission") from exc

    result = None
    try:
        result = triage.triage(payload)
        submissions.record_triage(reference, result)
    except triage.TriageUnavailable as exc:
        # LJ still gets the raw message; the email says triage did not run.
        print(f"warning: triage failed for {reference}: {exc}")

    try:
        notify.send(reference, payload, result)
        submissions.mark_notified(reference)
    except notify.NotificationFailed as exc:
        # Recoverable by hand: the row is in the store with notified = 0.
        print(f"warning: notification failed for {reference}: {exc}")

    return ContactResponse(received=True, reference=reference)


@app.get("/debug/error", include_in_schema=False)
def debug_error() -> None:
    """Raise on purpose, so a real error can be seen reaching Sentry.

    This is how the Step 2.5 verification is done: hit this once against the
    running VM and confirm the exception appears in the dashboard. Kept out of
    the OpenAPI schema so it is not advertised, and it carries no data — the
    message is a fixed string, nothing from the request — so triggering it
    reveals nothing. It stays because it is also the fastest way to confirm
    error reporting still works after any future change.
    """
    raise RuntimeError("Deliberate test error from /debug/error — Sentry wiring check.")
