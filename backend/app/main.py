"""FastAPI application for the AI portfolio backend.

Exposes the health check and the RAG chatbot. Contact triage (/contact) arrives
in Step 2.4.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import content, notify, observability, rag, ratelimit, submissions, triage
from app.config import (
    ALLOWED_ORIGINS,
    CONTACT_DAILY_LIMIT_TOTAL,
    RESUME_PDF_PATH,
)
from app.schemas import (
    AskContent,
    BrowserContent,
    ChatRequest,
    ChatResponse,
    ContactContent,
    ContactRequest,
    ContactResponse,
    ErrorResponse,
    ProfileContent,
    ProjectsContent,
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
contact_limiter = ratelimit.DailyRateLimiter(total_limit=CONTACT_DAILY_LIMIT_TOTAL)


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

# The web frontend calls this API from a different origin in production — see
# config.ALLOWED_ORIGINS. Without this, every browser fetch() fails with a
# generic "Failed to fetch" the browser never explains further, even though a
# plain curl (which doesn't enforce CORS) works fine.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)


class HealthResponse(BaseModel):
    """Response body for the health check."""

    status: str


@app.get("/health", response_model=HealthResponse)
@app.head("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report that the process is up.

    Deliberately dependency-free: no model call, no vector store, no disk I/O.
    An external uptime monitor and every post-deploy smoke test gate on this
    endpoint, so it must stay fast and must not fail because something
    downstream is unhealthy. Checks for those dependencies belong in a separate
    readiness endpoint if they are ever needed.

    HEAD is registered explicitly, not inherited from GET: UptimeRobot's free
    HTTP(s) monitor sends HEAD by default, and FastAPI does not add it to a
    route's allowed methods automatically — confirmed live, the monitor was
    getting a real 405 while every manual GET check returned 200.
    """
    return HealthResponse(status="ok")


# --- Content -------------------------------------------------------------
#
# Portfolio copy — see app/content.py. Each endpoint returns the same object
# loaded once at import; no per-request disk I/O, no rate limit (a static
# read, not something that costs money to serve).


@app.get("/content/profile", response_model=ProfileContent)
def content_profile() -> ProfileContent:
    """Hero copy — the web hero."""
    return content.PROFILE


@app.get("/content/browser", response_model=BrowserContent)
def content_browser() -> BrowserContent:
    """Web's on-device project-finder section copy."""
    return content.BROWSER


@app.get("/content/ask", response_model=AskContent)
def content_ask() -> AskContent:
    """Chat section copy."""
    return content.ASK


@app.get("/content/contact", response_model=ContactContent)
def content_contact() -> ContactContent:
    """Contact section copy."""
    return content.CONTACT


@app.get("/content/projects", response_model=ProjectsContent)
def content_projects() -> ProjectsContent:
    """The project cards — web's grid and its on-device finder."""
    return content.PROJECTS


@app.get("/resume")
def resume() -> FileResponse:
    """Serve the downloadable PDF resume.

    A static file read, same reasoning as /content/*: no rate limit, since it
    costs nothing to serve. `filename` gives the download a real name instead
    of the source file's on-disk name, and makes the browser treat this as an
    attachment rather than navigating to it inline.
    """
    return FileResponse(
        RESUME_PDF_PATH,
        media_type="application/pdf",
        filename="Ljuben-Vassilev-Resume.pdf",
    )


@app.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        429: {"model": ErrorResponse, "description": "Daily request limit reached"},
        503: {"model": ErrorResponse, "description": "Retrieval or the Z.AI API is unavailable"},
    },
)
def chat(payload: ChatRequest) -> ChatResponse:
    """Answer a visitor's question from the corpus.

    Rate limiting comes first, so an over-limit request costs nothing but the
    counter check. Inference is free now, so this ceiling is no longer a spend
    cap — it is a brake on how hard one day can hammer a 12 GB box that is also
    holding the embedding model.
    """
    try:
        limiter.check_and_count()
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
def contact(payload: ContactRequest, background: BackgroundTasks) -> ContactResponse:
    """Accept a contact submission, then triage and notify out of band.

    The order matters more than anything else here. The message is written to
    the store **first**, before any network call, so that neither the model
    being down nor Resend being down can lose it. Only a failure to store is
    fatal — at that point there is genuinely nothing holding their message, and
    saying so honestly beats a 200 that means nothing.

    Everything after the store runs in a background task, so the sender gets
    their acknowledgement in milliseconds. That is not a nicety. Three calls in
    four to the free model come back "overloaded" (config.py has the numbers),
    so triage only succeeds by retrying — up to forty attempts over two minutes.
    That budget is affordable *precisely because* nobody is waiting on it.
    Inline, the same reliability would mean a visitor watching a spinner past
    nginx's 60-second proxy timeout, which reads as broken however well it
    actually worked.
    """
    try:
        contact_limiter.check_and_count()
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

    background.add_task(_triage_and_notify, reference, payload)
    return ContactResponse(received=True, reference=reference)


def _triage_and_notify(reference: str, payload: ContactRequest) -> None:
    """Classify the submission and email LJ. Runs after the response is sent.

    Both steps are best-effort and log rather than raise: there is no longer a
    caller to fail, and the submission is already safely stored either way. If
    the process dies before this runs, the row is still there with
    `notified = 0`, which is the same recoverable state a failed send leaves.
    """
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
