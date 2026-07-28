# AI Showcase Portfolio

A portfolio site that deliberately demonstrates **four distinct AI deployment patterns** in one
project, backed by real infrastructure — provisioned, configured, and deployed by hand rather than
clicked together on a managed platform.

The point isn't that any single feature is hard. The point is that each one runs inference in a
*different place*, for a *different reason*, and the trade-offs behind those choices are the actual
content of the portfolio.

## The four inference layers

| Layer | Where it runs | What it does |
|---|---|---|
| **Browser** | Visitor's own device | On-device model (transformers.js) matches a question to my real projects — no network round-trip, no API cost |
| **Edge** | Cloudflare Workers AI | Pre-filters/classifies contact form submissions for spam before they reach the backend |
| **Server** | Oracle Cloud VM (Ampere A1, 2 OCPU / 12 GB) | RAG chatbot — embeddings + vector store — answers questions about my experience |
| **Cloud API** | Anthropic Claude API | Contact form triage (classify, extract, draft reply) + RAG generation |

## Repo layout

```
ai-portfolio/
├── web/          # One-pager: scroll animations, chat widget, on-device project finder
├── backend/      # FastAPI: contact triage + RAG chatbot
│   ├── app/
│   ├── data/     # source content for RAG
│   └── tests/
├── edge/         # Cloudflare Worker (Workers AI pre-filter)
├── docs/         # architecture.md, decisions.md, runbook.md
├── infra/        # nginx config, systemd units, VM bootstrap script
└── .github/workflows/   # path-filtered CI/CD to three separate targets
```

## Stack

| Component | Choice |
|---|---|
| Backend | Python + FastAPI |
| Vector store | SQLite-vec |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| Contact triage / RAG generation | Claude API |
| Browser on-device model | transformers.js — all-MiniLM-L6-v2 (ONNX, embeddings only — retrieval, not generation) |
| Edge pre-filter | Cloudflare Workers AI |
| Reverse proxy / TLS | nginx + Let's Encrypt |
| Process management | systemd |
| DNS / CDN | Cloudflare (proxied) |
| Error tracking | Sentry (backend + web) |
| Product analytics | PostHog (web) |

Rationale for each choice — including the ones that were rejected — lives in
[`docs/decisions.md`](docs/decisions.md).

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — diagram and walkthrough of all four inference layers
- [`docs/decisions.md`](docs/decisions.md) — decision log
- [`docs/runbook.md`](docs/runbook.md) — deploying, rotating secrets, restarting services

## Status

Under active construction. This README describes the intended end state; see the commit history
for what actually exists right now.
