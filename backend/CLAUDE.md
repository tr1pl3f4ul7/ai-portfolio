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
| Framework | FastAPI | **Python 3.11 locally, 3.12 on the VM and in CI** — see below |
| Vector store | `sqlite-vec` | Embedded — no separate service to run or monitor |
| Embeddings | `thenlper/gte-small` | 384-dim, 512-token window, CPU-only. Chosen by benchmark over the plan's `all-MiniLM-L6-v2` — decision 28 |
| LLM | Anthropic Claude API | `claude-haiku-4-5` for both `/chat` and triage — decision 30. Sonnet 5 if quality demands it |
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

Local setup — the PyTorch index is declared inside `requirements.txt`, so no extra flags:

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
```

Run and test:

```bash
uvicorn app.main:app --reload
pytest -v
```

**Never drop the `--extra-index-url` line from `requirements.txt`, and never unpin `torch`.** It is
not a Windows workaround — it is what keeps the CUDA toolkit out of every environment. PyPI's
default Linux torch pulls in several GB of `nvidia-*` packages, and nothing here has a GPU: not the
Ampere A1 VM, not the test container, not the CI runners.

## Running the full test suite

`sqlite-vec` has no Windows ARM64 wheel, so retrieval tests **cannot** run natively on the dev
machine — they skip via `importorskip`. A green `pytest` on Windows is therefore not proof.

Before presenting any retrieval work, run the whole suite on Linux:

```bash
cd backend/test && ./run-tests.sh
```

That builds a `linux/arm64` image matching the VM and runs everything. Source is bind-mounted, so
only a `requirements.txt` change forces a rebuild.

## Python 3.12 everywhere

| Where | Python |
|---|---|
| Dev machine | 3.12 |
| Oracle VM | 3.12 (Ubuntu 24.04 stock) |
| CI | 3.12 |

Decisions 19 and 23 in `docs/decisions.md` have the reasoning. **Target 3.12 in CI** — it mirrors
production.

⚠️ Python 3.11 is also installed on this machine and `python` on PATH may still resolve to it.
Create the venv with the 3.12 interpreter explicitly:

```
C:\Users\tr1pl3f4ul7\AppData\Local\Programs\Python\Python312-arm64\python.exe -m venv .venv
```

Check with `.venv\Scripts\python --version` before installing anything.
