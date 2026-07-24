"""FastAPI application for the AI portfolio backend.

Exposes the health check and the RAG chatbot. Contact triage (/contact) arrives
in Step 2.4.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from app import rag, ratelimit
from app.schemas import ChatRequest, ChatResponse, ErrorResponse, Source

limiter = ratelimit.DailyRateLimiter()


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
