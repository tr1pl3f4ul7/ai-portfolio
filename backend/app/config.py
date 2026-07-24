"""Application configuration.

The only place in the backend that reads os.environ. Everything else imports
from here, so there is exactly one list of what this service can be configured
with and exactly one place to change a default.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Local development only. `.env` is gitignored and holds the Anthropic key; on
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
# is cheap next to the answer Claude generates from it.
TOP_K = int(os.environ.get("AI_PORTFOLIO_TOP_K", "6"))

# ---------------------------------------------------------------------------
# Claude API
# ---------------------------------------------------------------------------

# Never has a default. An unset key must fail loudly at first use rather than
# silently fall back to something.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Haiku 4.5 — LJ's call, and the right shape for this job. The answer is
# generated from context that has already been retrieved and ranked; the model
# is summarising supplied text, not reasoning from scratch. Haiku is a fifth the
# price of Opus per token and noticeably faster, which matters for a chat widget
# a visitor is waiting on. Switch to claude-sonnet-5 here if answer quality
# disappoints — this is the only line that needs to change.
ANTHROPIC_MODEL = os.environ.get("AI_PORTFOLIO_ANTHROPIC_MODEL", "claude-haiku-4-5")

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
# Two ceilings, both counted per calendar day in UTC and both reset at the same
# instant: one per client IP, and one across every caller. The per-IP limit
# stops a single visitor draining the budget; the total is the actual spend cap,
# and it holds even against traffic spread across many addresses.
#
# UTC rather than Brisbane time so the reset is deterministic and does not move
# with daylight saving anywhere. The consequence is that the window rolls over
# at 10am local, not midnight — fine for a spend cap, worth knowing when reading
# the numbers.
CHAT_DAILY_LIMIT_PER_IP = int(os.environ.get("AI_PORTFOLIO_CHAT_LIMIT_PER_IP", "20"))
CHAT_DAILY_LIMIT_TOTAL = int(os.environ.get("AI_PORTFOLIO_CHAT_LIMIT_TOTAL", "500"))

# /contact gets its own counters, much tighter. A person submits a contact form
# roughly once; twenty attempts from one address is not a person. Sharing
# /chat's counters would let chatbot traffic exhaust LJ's ability to receive
# mail, which is the more valuable of the two endpoints.
CONTACT_DAILY_LIMIT_PER_IP = int(os.environ.get("AI_PORTFOLIO_CONTACT_LIMIT_PER_IP", "5"))
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

# Same model as /chat. Classifying a short message and drafting a two-line reply
# is comfortably within Haiku, and the draft is a starting point for LJ to edit
# rather than anything sent automatically.
TRIAGE_MODEL = os.environ.get("AI_PORTFOLIO_TRIAGE_MODEL", "claude-haiku-4-5")
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
