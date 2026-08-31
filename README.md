# AI Showcase Portfolio

**Live at [ljubenvassilev.com](https://ljubenvassilev.com)** · [uptime status](https://stats.uptimerobot.com/jGsw934M4A)

Built entirely through prompts to Claude Code — every line of application code, every
infrastructure script, every CI/CD workflow, and every word of documentation, including this
sentence. Not a single file in this repository was hand-edited.

A portfolio site that deliberately demonstrates **four distinct AI deployment patterns** in one
project, backed by real infrastructure. Claude Code wrote every script and config file, but
provisioning the Oracle Cloud VM, wiring up its firewall, cutting over DNS, installing the TLS
certificate, and running each deploy step against a live machine was hands-on systems
administration — not a managed platform's one-click deploy.

The point isn't that any single feature is hard. The point is that each one runs inference in a
*different place*, for a *different reason*, and the trade-offs behind those choices are the actual
content of the portfolio. `docs/architecture.md` walks through all four; this README is the front
door.

## The four inference layers

| Layer | Where it runs | What it does |
|---|---|---|
| **Browser** | Visitor's own device | On-device model (transformers.js) matches a question to my real projects — no network round-trip, no API cost |
| **Edge** | Cloudflare Workers AI | Pre-filters/classifies contact form submissions for spam before they reach the backend |
| **Server** | Oracle Cloud VM (Ampere A1, 2 OCPU / 12 GB) | RAG chatbot — embeddings + vector store — answers questions about my experience |
| **Cloud API** | Z.AI GLM-4.7-Flash | Contact form triage (classify, extract, draft reply) + RAG generation |

## Repo layout

```
ai-portfolio/
├── web/          # One-pager: scroll animations, chat widget, on-device project finder
├── backend/      # FastAPI: contact triage + RAG chatbot
│   ├── app/
│   ├── data/     # source content for RAG
│   └── tests/
├── edge/         # Cloudflare Worker (Workers AI pre-filter)
├── docs/         # architecture, decisions, design system, build plan — see below
├── infra/        # nginx config, systemd units, VM bootstrap script
└── .github/workflows/   # path-filtered CI/CD to three separate targets
```

## Stack

| Component | Choice |
|---|---|
| Backend | Python + FastAPI |
| Vector store | SQLite-vec |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| Contact triage / RAG generation | Z.AI GLM API |
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

Five files, each answering a different question — start with whichever one matches yours:

| File | Answers | Read it if you want to know... |
|---|---|---|
| [`docs/architecture.md`](docs/architecture.md) | *How does it actually work?* | What each of the four layers does, mechanically, and why it lives where it lives. Start here. |
| [`docs/decisions.md`](docs/decisions.md) | *Why this choice, not another?* | The full decision log — every non-obvious call made while building this, what was rejected instead, and why. `architecture.md` cites specific entries by number throughout. |
| [`docs/design-system.md`](docs/design-system.md) | *Why does it look like this?* | The visual language — colour, type, motion — and why the terminal-native, dark-only direction was chosen over the alternatives. |
| [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) | *How was this actually built?* | The original step-by-step build plan, worked through one verified step at a time from an empty repo to what's live now. |
| [`docs/future-enhancements.md`](docs/future-enhancements.md) | *What's deliberately not here yet?* | Ideas explicitly deferred until the plan above was finished, so the scope decision is on record rather than a matter of memory. |

## Status

Live and complete — every phase in `docs/PROJECT_PLAN.md` is built, deployed, and verified,
including this README. `docs/decisions.md` is the record of everything that changed along the way,
including the one phase (a Flutter mobile app) that was built partway through and then deliberately
removed — see decision 64.
