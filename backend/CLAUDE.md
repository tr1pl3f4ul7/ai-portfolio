# backend/ — FastAPI RAG + Contact Triage

The **server** inference layer. Runs on the Oracle Ampere A1 VM behind nginx, managed by systemd.

Two jobs:
1. **RAG chatbot** (`/chat`) — embed the query, retrieve top-k chunks from a local vector store,
   call Claude with that context, return a grounded answer.
2. **Contact triage** (`/contact`) — hand a submission to Claude for intent classification, field
   extraction, and a draft reply; store it; notify LJ.

## Stack

| Concern | Choice | Notes |
|---|---|---|
| Framework | FastAPI (Python 3.11) | |
| Vector store | `sqlite-vec` | Embedded — no separate service to run or monitor |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` | 384-dim, CPU-only, ARM64-friendly |
| LLM | Anthropic Claude API | Haiku for triage (cost), Sonnet if quality demands it |
| Errors | `sentry-sdk` FastAPI integration | Phase 2.5 |
| Tests | `pytest` + `TestClient` | |
| Process | systemd unit → uvicorn | See `infra/systemd/` |

## Intended layout

Files arrive in the step that owns them — **don't pre-create them.**

```
backend/
├── app/
│   ├── main.py        # FastAPI app, route registration, Sentry init
│   ├── config.py      # Settings from env vars — the ONLY place os.environ is read
│   ├── schemas.py     # Pydantic request/response models, shared with web + mobile
│   ├── rag.py         # embed → retrieve → build prompt → call Claude
│   ├── triage.py      # contact classification/extraction/draft reply
│   └── ingest.py      # chunk + embed source content into the vector store  (Step 2.2)
├── data/              # RAG source content (resume, project write-ups) — committed
│                      # Generated *.db / *.sqlite are gitignored, NOT committed
└── tests/
```

`data/` holds the **source** material as text/markdown, which is committed and reviewable. The
embedded index built from it is a build artefact — regenerate it, don't commit it.

## Rules

- **All config through `config.py`.** Read `os.environ` in exactly one place. Never inline an
  env var lookup in a route handler.
- **Never live-call the Claude API in automated tests.** Mock the client. One manual smoke test
  against the real API is fine — run it by hand, keep it out of CI.
- **Load the embedding model once at startup**, not per request. It's ~90 MB resident; the VM
  has 12 GB shared with nginx and the OS.
- **Every endpoint gets a Pydantic response model.** The web and mobile clients both depend on
  these shapes — they're the contract.
- `/health` must stay dependency-free and fast. An uptime monitor hits it every few minutes and
  the deploy smoke test gates on it. Don't make it call Claude or touch the vector store.
- Secrets come from the environment. `ANTHROPIC_API_KEY` never appears in source, tests,
  fixtures, or log output.

## Commands

Local setup (**note the extra index — required on this ARM64 machine**):

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

Run and test:

```bash
uvicorn app.main:app --reload
pytest -v
```

The extra index URL is a **local-only** workaround. The VM and CI run Linux `aarch64`, where
plain PyPI has native torch wheels — don't add it there.
