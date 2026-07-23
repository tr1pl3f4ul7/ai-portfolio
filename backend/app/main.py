"""FastAPI application for the AI portfolio backend.

Currently exposes only the health check. The RAG chatbot (/chat) and contact
triage (/contact) endpoints arrive in later steps of the build plan.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="AI Portfolio API",
    description="RAG chatbot and contact triage for the AI showcase portfolio.",
    version="0.1.0",
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
