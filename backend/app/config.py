"""Application configuration.

The only place in the backend that reads os.environ. Everything else imports
from here, so there is exactly one list of what this service can be configured
with and exactly one place to change a default.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Local development only. `.env` is gitignored and holds the Z.AI key; on
# the VM the same variables arrive from the systemd unit and in CI from GitHub
# Actions secrets, where no .env file exists and this is a no-op. Real
# environment variables win over the file, so the VM cannot be shadowed by a
# stray .env that got copied there.
load_dotenv(BACKEND_ROOT / ".env", override=False)

# Source content for retrieval. Markdown files are the source of truth; the
# vector store is a build artefact regenerated from them.
DATA_DIR = Path(os.environ.get("AI_PORTFOLIO_DATA_DIR", BACKEND_ROOT / "data"))

# Vector store location. Gitignored — rebuilt by `python -m app.ingest`.
DB_PATH = Path(os.environ.get("AI_PORTFOLIO_DB_PATH", BACKEND_ROOT / "data" / "vectors.db"))

# Chosen by measurement, not reputation — see backend/test/compare_models.py and
# decision 28. Against the real corpus and the real evaluation queries:
#
#   model                    dims  max_seq  truncated  top-4  top-6
#   all-MiniLM-L6-v2          384      256       3/56    4/8    6/8   <- plan's choice
#   all-MiniLM-L12-v2         384      128      23/56    5/8    6/8
#   bge-small-en-v1.5         384      512          0    5/8    6/8
#   gte-small                 384      512          0    6/8    7/8   <- selected
#   all-mpnet-base-v2         768      384          0    4/8    5/8
#
# gte-small keeps 384 dimensions, so the sqlite-vec schema is unchanged, and its
# 512-token window means nothing in the corpus is truncated. Note all-mpnet-base
# is nine times slower and scored worst; bigger was not better here.
EMBEDDING_MODEL = os.environ.get("AI_PORTFOLIO_EMBEDDING_MODEL", "thenlper/gte-small")
EMBEDDING_DIMENSIONS = 384

# Who the corpus is about. Prepended to every chunk before embedding, so a
# section retrieved in isolation still says whose experience it describes.
CORPUS_SUBJECT = os.environ.get("AI_PORTFOLIO_CORPUS_SUBJECT", "Ljuben Vassilev")

# Chunks retrieved per query.
#
# 6 rather than 4. Measured on the real corpus: several correct chunks landed at
# rank 5, losing to FAQ entries by margins as small as 0.0075 — the FAQ is
# written as questions, so it competes strongly with anything question-shaped.
# At a median 112 tokens per chunk this is roughly 670 tokens of context, which
# is cheap next to the answer the model generates from it.
TOP_K = int(os.environ.get("AI_PORTFOLIO_TOP_K", "6"))

# ---------------------------------------------------------------------------
# Z.AI GLM API
# ---------------------------------------------------------------------------

# Never has a default. An unset key must fail loudly at first use rather than
# silently fall back to something.
ZAI_API_KEY = os.environ.get("ZAI_API_KEY", "")

# Plain REST — a bearer token and JSON, no vendor SDK. The chat-completions
# path is appended by app/llm.py.
ZAI_BASE_URL = os.environ.get("AI_PORTFOLIO_ZAI_BASE_URL", "https://api.z.ai/api/paas/v4")

# GLM-4.7-Flash, for both /chat and contact triage.
#
# Z.AI prices exactly two text models at zero. Measured against the live API,
# eight sequential calls each:
#
#   glm-4.7-flash   2/8 succeeded   ~1-2s on success, ~0.4s to fail (429/1305)
#   glm-4.5-flash   8/8 succeeded   36-65s per call
#
# 4.5-Flash is reliable and unusably slow — a minute per call, against nginx's
# 60s proxy timeout. So both endpoints use 4.7-Flash and treat its failures as
# the thing to engineer around rather than a reason to pick the other one.
#
# Free on Z.AI means shared best-effort capacity: roughly three calls in four
# return "service temporarily overloaded". That is survivable only because the
# failure is *cheap* — a 429 comes back in ~0.4s where an answer takes 1-2s —
# so retrying costs almost nothing. app/llm.py spends those failures on retries,
# with two budgets: a short one for /chat, where a visitor is watching, and a
# much longer one for triage, which runs in a background task where nobody is.
#
# The escape hatch, if this ever stops holding: GLM-5.3-Flash, 50 concurrent,
# fast and reliable, at $0.15/$0.50 per million tokens — cents a month at this
# traffic. It needs a positive account balance; without one it returns
# "1113 Insufficient balance" rather than an answer.
ZAI_MODEL = os.environ.get("AI_PORTFOLIO_ZAI_MODEL", "glm-4.7-flash")

# Deliberately small. Portfolio answers should be a few short paragraphs, the
# system prompt asks for exactly that, and a low ceiling caps the cost of a
# runaway generation. Raise it if answers start arriving truncated.
ANSWER_MAX_TOKENS = int(os.environ.get("AI_PORTFOLIO_ANSWER_MAX_TOKENS", "1024"))

# Longest question accepted. A portfolio question is a sentence or two; anything
# past this is either an accident or an attempt to stuff the prompt.
MAX_QUESTION_CHARS = int(os.environ.get("AI_PORTFOLIO_MAX_QUESTION_CHARS", "1000"))

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
#
# One ceiling per endpoint, counted per calendar day in UTC.
#
# There used to be a second, per-client-IP ceiling. It existed because every
# request spent money at the Claude API, so the total was a spend cap and the
# per-IP limit was what stopped one visitor draining it. Z.AI's free models are
# not metered by token or request at all — only by concurrency — so there is no
# budget left to drain and the per-IP counter was protecting nothing.
#
# Known consequence, accepted deliberately: without it, one caller can spend the
# whole daily total on its own. For /chat that is a self-limiting nuisance. For
# /contact it is real — the total below is what keeps submissions inside
# Resend's own free-tier ceiling, and a script can now exhaust it in a minute
# and lock out every genuine enquiry until the next UTC midnight. Restore a
# per-IP counter here if that ever actually happens.
#
# UTC rather than Brisbane time so the reset is deterministic and does not move
# with daylight saving anywhere. The consequence is that the window rolls over
# at 10am local, not midnight — worth knowing when reading the numbers.
CHAT_DAILY_LIMIT_TOTAL = int(os.environ.get("AI_PORTFOLIO_CHAT_LIMIT_TOTAL", "500"))

# /contact gets its own counter, much tighter, and keeps it for a reason that
# survived the change above: this one is not about inference cost. Every
# submission sends mail through Resend, whose free tier has a hard daily
# ceiling, and sharing /chat's counter would let chatbot traffic exhaust LJ's
# ability to receive mail — the more valuable of the two endpoints.
CONTACT_DAILY_LIMIT_TOTAL = int(os.environ.get("AI_PORTFOLIO_CONTACT_LIMIT_TOTAL", "50"))

# ---------------------------------------------------------------------------
# Contact triage and notification
# ---------------------------------------------------------------------------

# Deliberately NOT vectors.db. Decision 27 has ingestion rebuild the vector
# store from scratch on every deploy — it is a disposable build artefact. A
# visitor's message is the opposite of disposable, so it lives in its own file
# that nothing regenerates.
SUBMISSIONS_DB_PATH = Path(
    os.environ.get("AI_PORTFOLIO_SUBMISSIONS_DB_PATH", BACKEND_ROOT / "data" / "submissions.db")
)

# Triage runs on ZAI_MODEL, the same model as /chat — classifying a short
# message and drafting a two-line reply is comfortably within a Flash-tier
# model, and the draft is a starting point for LJ to edit rather than anything
# sent automatically. Only the token ceiling differs, and only so the two can be
# tuned apart.
TRIAGE_MAX_TOKENS = int(os.environ.get("AI_PORTFOLIO_TRIAGE_MAX_TOKENS", "1024"))

# Field ceilings for the contact form. Generous enough for a real enquiry,
# small enough that the endpoint is not a free way to push 200 KB into a model.
MAX_NAME_CHARS = int(os.environ.get("AI_PORTFOLIO_MAX_NAME_CHARS", "120"))
MAX_MESSAGE_CHARS = int(os.environ.get("AI_PORTFOLIO_MAX_MESSAGE_CHARS", "5000"))

# Resend, over HTTPS to api.resend.com:443 — chosen partly because Oracle Cloud
# blocks outbound SMTP (25/465/587) by default, so a mail library would need a
# support request before it ever sent anything. See decision 33.
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

# Where the notification lands. No default: an unset recipient must fail loudly
# rather than silently drop LJ's mail somewhere.
CONTACT_NOTIFY_TO = os.environ.get("CONTACT_NOTIFY_TO", "")

# Resend's shared sender, which may only deliver to the account owner's own
# address. That restriction is exactly the requirement here — the notification
# goes to LJ and nobody else — so no domain verification is needed. Point this
# at a verified ljubenvassilev.com address if that ever changes.
CONTACT_NOTIFY_FROM = os.environ.get("AI_PORTFOLIO_CONTACT_FROM", "onboarding@resend.dev")

# ---------------------------------------------------------------------------
# Resume download
# ---------------------------------------------------------------------------

# Served as-is by GET /resume. Source is backend/static/resume.html; the PDF
# is regenerated by hand and committed alongside it, the same pattern as
# design/tokens.json -> web/src/styles/tokens.css.
RESUME_PDF_PATH = BACKEND_ROOT / "static" / "resume.pdf"

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

# The web frontend and this API are different origins in production
# (ljubenvassilev.com vs api.ljubenvassilev.com — decision 48's domain split),
# so browser requests need an explicit allowlist or every fetch() fails with a
# generic "Failed to fetch" the browser refuses to explain further. Local dev
# never exercises this: Vite's dev proxy makes browser requests same-origin
# (web/vite.config.ts). Comma-separated so a future origin can be added
# without a code change.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "AI_PORTFOLIO_ALLOWED_ORIGINS",
        "https://ljubenvassilev.com,https://www.ljubenvassilev.com",
    ).split(",")
    if origin.strip()
]

# ---------------------------------------------------------------------------
# Error tracking (Sentry)
# ---------------------------------------------------------------------------

# Empty means disabled, which is the correct default: locally and in tests
# nothing should be shipped to a third party. Set it on the VM (and only there)
# to turn error reporting on. The DSN is write-only — it can send events, not
# read them — so it is less sensitive than an API key, but it still identifies
# the project and still lives in .env, never in the repo.
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

# Tags every event so production errors are not mixed with anything else. When
# the CI pipeline runs the backend it should set this to something like "ci".
SENTRY_ENVIRONMENT = os.environ.get("AI_PORTFOLIO_ENV", "development")

# Fraction of requests traced for performance. 0.1 is plenty of signal on a
# low-traffic portfolio without generating much data; every *error* is still
# captured regardless of this — it governs performance spans, not exceptions.
SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("AI_PORTFOLIO_SENTRY_TRACES", "0.1"))
