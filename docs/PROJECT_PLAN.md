# AI Showcase Portfolio — Master Build Plan

**Purpose of this file**: hand this to Claude Code as the working spec. Claude Code should work through phases in order, doing everything it can autonomously (scaffolding, code, config files, GitHub Actions, non-interactive CLI steps), and only stopping to prompt LJ for the tasks explicitly tagged `🧑 MANUAL`.

Each phase lists tasks tagged:
- `🤖 CLAUDE CODE` — do this autonomously
- `🧑 MANUAL` — requires LJ (account creation, payment info, clicking through a web console, approving something, copying a secret)
- `✅ VERIFY` — a checkpoint where Claude Code stops and LJ confirms the step actually works before anything else proceeds

### Working protocol — strict, sequential, verified
This project is built **one step at a time, not one phase at a time**. For every numbered step below:
1. Claude Code implements only that step (not ahead of it).
2. Claude Code runs the tests for that step itself and reports the result.
3. Claude Code presents LJ with a concrete way to verify the step (a command to run, a URL to open, an output to check).
4. Claude Code **stops and waits** for LJ's explicit confirmation before starting the next step.
5. If verification fails, Claude Code fixes the issue and repeats from step 2 before moving on.

No step should be started while a previous step's `✅ VERIFY` is still outstanding.

### Testing standard applied throughout
Every step that produces code or config includes its own testing task, following standard practice for that layer:
- **Backend (FastAPI)**: `pytest` unit tests for logic (classification parsing, retrieval ranking), integration tests for endpoints using `httpx`/`TestClient`, mocked Claude API calls in CI (no live API calls in automated tests)
- **Edge (Cloudflare Worker)**: `vitest` with `@cloudflare/vitest-pool-workers` for unit tests; local `wrangler dev` smoke test before deploy
- **Web**: basic component/interaction tests (Playwright or Vitest depending on framework chosen) plus a manual cross-browser smoke check for the WebLLM widget
- **Flutter**: widget tests for UI, unit tests for API client and on-device inference wrapper, `flutter test` in CI
- **Infra**: idempotency check on `setup.sh` (safe to re-run), a post-deploy smoke test hitting `/health` after every backend deploy

---

## 1. Project Summary

A portfolio site that deliberately demonstrates four distinct AI deployment patterns in one project, backed by real infrastructure LJ built and configured himself:

| Layer | Where it runs | What it does |
|---|---|---|
| Browser (client-side) | Visitor's device | On-device LLM summarizes LJ's experience via WebLLM |
| Edge | Cloudflare Workers AI | Pre-filters/classifies contact form submissions for spam before they reach the backend |
| Server | Oracle Cloud VM (Ampere A1, 2 OCPU/12GB) | RAG chatbot (embeddings + vector store) answers questions about LJ's experience |
| Cloud API | Anthropic Claude API | Contact form triage (classify, extract fields, draft reply) + RAG generation |

Plus: a Flutter mobile app reusing the same backend, with on-device summarization via `flutter_local_ai`.

Everything lives in one monorepo with path-filtered GitHub Actions CI/CD deploying to four separate targets (Oracle VM, Cloudflare Workers, GitHub Pages/Cloudflare Pages for web, and mobile build artifacts).

---

## 2. Locked-In Tech Stack Decisions

| Component | Choice | Why |
|---|---|---|
| Backend framework | Python + FastAPI | Best ecosystem for embeddings/RAG, aligns with LJ's AI engineering cert path |
| Vector store | SQLite-vec (or Chroma if simpler) | Embedded, no separate service, fine at portfolio scale |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` | Small, CPU-friendly, ARM64-compatible |
| Contact form triage | Claude API (Haiku for cost, Sonnet if quality needed) | Structured JSON output: intent classification + field extraction + draft reply |
| Browser on-device model | WebLLM, Llama-3.2-1B-Instruct or Qwen2.5-0.5B-Instruct (MLC quantized) | Small enough for reasonable download size |
| Mobile on-device model | `flutter_local_ai` (wraps Apple's on-device Foundation Models on iOS and Gemini Nano/ML Kit GenAI on Android) | Uses each platform's built-in on-device AI rather than bundling a model — no download size, native performance |
| Edge pre-filter | Cloudflare Workers AI, small model (e.g. `@cf/meta/llama-3.2-1b-instruct`) | Spam/intent pre-check before hitting Claude API |
| Reverse proxy / TLS | nginx + certbot (Let's Encrypt) | Standard, well-documented |
| Process management | systemd service for FastAPI app | Simple, no extra orchestration needed at this scale |
| DNS / CDN | Cloudflare (proxied) | Handles DNS, proxying, and TLS for the domain |
| Mobile framework | Flutter | Matches LJ's existing mobile experience, single codebase both stores |
| Monorepo | Yes, single repo | One README tells the whole story; shared contracts (API schemas) live in one place |
| Error tracking / crash reporting | Sentry (backend, web, mobile) | Same tool, same dashboard, across three completely different runtimes (Python, browser JS, Flutter) — a stronger "one coherent observability story" than splitting tools per platform |
| Product analytics | PostHog (web + mobile) | Autocapture, session replay, and event tracking from one SDK family across both surfaces; open-source with a generous free tier |

**Note on analytics/crash reporting choice**: Firebase (Analytics + Crashlytics) and Supabase were both considered. Firebase is a fine default but is so common it doesn't differentiate much, and using Supabase for web analytics while Firebase for mobile would mean two unrelated tools with no shared reasoning behind the split. Sentry + PostHog were chosen instead because each is a *single* tool spanning multiple layers of the stack (Sentry across backend/web/mobile; PostHog across web/mobile), which tells a more deliberate story than picking one tool per platform.

---

## 3. Repo Structure

```
ai-portfolio/
├── web/                    # One-pager: HTML/CSS/JS (or lightweight framework), scroll animations, WebLLM widget
├── mobile/                 # Flutter app
├── backend/                # FastAPI app: contact form triage + RAG chatbot
│   ├── app/
│   ├── data/               # source content for RAG (resume, project descriptions)
│   └── tests/
├── edge/                   # Cloudflare Worker (Workers AI pre-filter)
├── docs/
│   ├── architecture.md     # Mermaid diagram + explanation of all 4 inference layers
│   ├── decisions.md        # Decision log (why Ampere A1, why Cloudflare Workers AI, why Flutter, etc.)
│   └── runbook.md          # How to deploy, rotate secrets, restart services
├── .github/
│   └── workflows/
│       ├── backend-ci.yml
│       ├── backend-deploy.yml
│       ├── edge-deploy.yml
│       ├── web-deploy.yml
│       └── mobile-build.yml
├── infra/
│   ├── nginx/              # nginx config templates
│   ├── systemd/            # service unit files
│   └── setup.sh            # one-shot VM bootstrap script
└── README.md
```

---

## 4. Build Phases

Each phase is broken into individual steps. Do not start step N+1 until step N's `✅ VERIFY` has been explicitly confirmed by LJ.

### Phase 0 — Prerequisites

**Step 0.1 — Accounts**
- `🧑 MANUAL`: Create Oracle Cloud account (credit card required for identity verification, usage stays in free tier)
- `🧑 MANUAL`: Create Cloudflare account, add the domain (LJ must already own or purchase it through a registrar)
- `🧑 MANUAL`: Create/confirm Anthropic API account, generate an API key
- `🧑 MANUAL`: Create a new empty GitHub repo, grant Claude Code push access
- `🧑 MANUAL`: Generate an SSH key pair for VM access if one doesn't exist
- `✅ VERIFY`: LJ confirms all accounts exist and the API key / SSH key are in hand

**Step 0.2 — Repo scaffold**
- `🤖 CLAUDE CODE`: Create the monorepo folder structure (Section 3), initialize git, add `.gitignore`, first commit, push to the empty GitHub repo
- `🤖 CLAUDE CODE`: Test: confirm `git clone` of the fresh repo on a clean path succeeds and matches expected structure
- `✅ VERIFY`: LJ clones the repo locally and confirms the structure looks right

---

### Phase 1 — Oracle VM Provisioning

**Step 1.1 — Create the instance**
- `🧑 MANUAL`: In Oracle Cloud console, create a VCN (or use quickstart default), create an Ampere A1 Flex instance sized to **2 OCPU / 12GB RAM** (current Always Free limit — do not request 4/24), Ubuntu 22.04 or 24.04, paste in the SSH public key, open ports 80/443 in the security list
- `🧑 MANUAL`: Provide the instance's public IP, confirm `ssh` access works
- `✅ VERIFY`: LJ confirms SSH login succeeds

**Step 1.2 — Bootstrap script**
- `🤖 CLAUDE CODE`: Write `infra/setup.sh` (updates, nginx, certbot, python3.11/pip, app user, `ufw` rules)
- `🤖 CLAUDE CODE`: Test: script is idempotent — write a check that running it twice produces no errors and no duplicate config; lint with `shellcheck`
- `✅ VERIFY`: LJ runs the script on the real VM (or approves Claude Code doing so via SSH) and confirms nginx is reachable on port 80 with the default page

---

### Phase 2 — Backend API (FastAPI)

**Step 2.1 — Skeleton + health check**
- `🤖 CLAUDE CODE`: Scaffold FastAPI app with just `GET /health` (checks process is up; Claude API/vector store checks added later once those exist)
- `🤖 CLAUDE CODE`: Test: `pytest` test hitting `/health` via `TestClient`, asserts 200
- `✅ VERIFY`: LJ confirms tests pass locally

**Step 2.2 — RAG ingestion**
- `🧑 MANUAL`: Provide resume/project content to embed (or confirm using existing portfolio copy)
- `🤖 CLAUDE CODE`: Write ingestion script (chunk, embed via `all-MiniLM-L6-v2`, store in SQLite-vec)
- `🤖 CLAUDE CODE`: Test: unit test asserting a known query returns the expected chunk in top-k results
- `✅ VERIFY`: LJ reviews a sample of retrieved chunks for a few test questions and confirms relevance

**Step 2.3 — `/chat` endpoint**
- `🧑 MANUAL`: Provide Anthropic API key as an environment variable (never hardcoded)
- `🤖 CLAUDE CODE`: Build `POST /chat` — embed query, retrieve top-k, call Claude API with context, return answer
- `🤖 CLAUDE CODE`: Test: integration test with the Claude API call mocked, asserting correct prompt construction and response parsing; one manual smoke test against the real API (not run in CI)
- `✅ VERIFY`: LJ asks the running endpoint a few real questions and confirms answers are accurate and grounded

**Step 2.4 — `/contact` endpoint**
- `🤖 CLAUDE CODE`: Build `POST /contact` — accepts payload, calls Claude API for classification/extraction/draft reply, stores submission, sends notification
- `🧑 MANUAL`: Confirm notification channel (email/SMTP vs. webhook) and provide credentials
- `🤖 CLAUDE CODE`: Test: mocked-API unit tests for classification parsing edge cases (malformed input, missing fields), integration test for the full endpoint
- `✅ VERIFY`: LJ submits a real test message and confirms they receive the notification with a sensible triage summary

**Step 2.5 — Error tracking (Sentry)**
- `🧑 MANUAL`: Create a free Sentry account/project for the backend, provide the DSN
- `🤖 CLAUDE CODE`: Integrate `sentry-sdk` (FastAPI integration) — captures unhandled exceptions and performance traces
- `🤖 CLAUDE CODE`: Test: trigger a deliberate test exception locally and confirm it's caught (mocked transport in automated tests, real send verified manually)
- `✅ VERIFY`: LJ confirms the test exception appears in the Sentry dashboard

**Step 2.6 — Deploy to VM**
- `🤖 CLAUDE CODE`: Write systemd unit file, deploy backend to the VM, start the service
- `🤖 CLAUDE CODE`: Test: post-deploy smoke test script hitting `/health`, `/chat`, `/contact` against the live VM
- `✅ VERIFY`: LJ hits the live VM's `/health` from their own machine and confirms 200

---

### Phase 3 — Web Frontend

**Step 3.1 — Static structure + design direction**
- `🤖 CLAUDE CODE`: Propose 1–2 visual design directions (layout, palette, animation style) before building
- `🧑 MANUAL`: Review and pick a direction
- `✅ VERIFY`: LJ approves the direction

**Step 3.2 — Build the one-pager**
- `🤖 CLAUDE CODE`: Build the page with scroll-triggered animations, contact form wired to `/contact`, chat widget wired to `/chat`
- `🤖 CLAUDE CODE`: Test: component/interaction tests for the form and chat widget; a basic cross-browser smoke check
- `✅ VERIFY`: LJ opens the page locally, submits the form, uses the chat widget, confirms both work end-to-end

**Step 3.3 — Browser on-device summarizer**
- `🤖 CLAUDE CODE`: Add "Summarize my experience" button using WebLLM with a small quantized model
- `🤖 CLAUDE CODE`: Test: verify model loads and produces output in at least one browser (Chrome), document expected load time
- `✅ VERIFY`: LJ clicks the button in their own browser and confirms it produces a sensible summary without hitting the backend

**Step 3.4 — Analytics and error tracking**
- `🧑 MANUAL`: Create Sentry project for web (or reuse backend project as a separate environment) and PostHog project, provide keys
- `🤖 CLAUDE CODE`: Integrate Sentry browser SDK (error/performance tracking) and PostHog JS SDK (autocapture + key events: form submit, chat used, summarizer used)
- `🤖 CLAUDE CODE`: Test: trigger a deliberate JS error and confirm capture; confirm a test event appears in PostHog
- `✅ VERIFY`: LJ confirms both a test error (Sentry) and a test event (PostHog) show up in their respective dashboards

---

### Phase 4 — Cloudflare Workers AI Edge Pre-filter

**Step 4.1 — Worker script**
- `🧑 MANUAL`: Enable Workers AI on the Cloudflare account, provide account ID / API token for `wrangler`
- `🤖 CLAUDE CODE`: Write Worker that runs a small Workers AI model to flag spam/low-quality submissions, forwards clean ones to `/contact`
- `🤖 CLAUDE CODE`: Test: `vitest` unit tests for the filtering logic; local `wrangler dev` smoke test with sample clean/spam payloads
- `✅ VERIFY`: LJ sends one obviously-spam and one legit test submission through the Worker locally and confirms correct routing

**Step 4.2 — Deploy the Worker**
- `🤖 CLAUDE CODE`: Deploy via `wrangler deploy`
- `✅ VERIFY`: LJ confirms the deployed Worker URL responds correctly to both test cases

---

### Phase 5 — Domain, DNS, TLS

**Step 5.1 — DNS cutover**
- `🧑 MANUAL`: Point domain's nameservers to Cloudflare (at the registrar)
- `🤖 CLAUDE CODE`: Configure DNS records in Cloudflare (A record → VM IP, proxied), configure Worker route
- `✅ VERIFY`: LJ confirms `dig`/`nslookup` on the domain resolves as expected and propagation looks complete

**Step 5.2 — TLS**
- `🤖 CLAUDE CODE`: Set up TLS (certbot on the VM, or Cloudflare edge TLS + origin cert — confirm "full strict" mode is wanted)
- `✅ VERIFY`: LJ opens the live domain over HTTPS and confirms a valid certificate with no browser warnings

---

### Phase 6 — CI/CD (GitHub Actions)

Covers the three targets that already exist (backend, edge, web). Mobile's own CI/CD — including
store publishing — is Step 7.5, once Phase 7 has actually built something to publish.

**Step 6.1 — Secrets**
- `🧑 MANUAL`: Add required secrets to GitHub repo settings — Claude Code lists exact names needed (see Section 5)
- `✅ VERIFY`: LJ confirms secrets are added

**Step 6.2 — CI workflows**
- `🤖 CLAUDE CODE`: `backend-ci.yml` (lint/test on push to `backend/**`), `edge-ci.yml` (Worker tests on push to `edge/**`), `web-ci.yml` (vitest on push to `web/**`)
- `🤖 CLAUDE CODE`: Test: push a trivial change to each path and confirm the right workflow triggers and passes
- `✅ VERIFY`: LJ checks the Actions tab and confirms green runs

**Step 6.3 — Deploy workflows**
- `🤖 CLAUDE CODE`: `backend-deploy.yml` (SSH deploy + systemd restart, path-filtered), `edge-deploy.yml` (`wrangler deploy`), `web-deploy.yml` (Cloudflare Pages, per decision 48)
- `🤖 CLAUDE CODE`: Test: each deploy workflow includes a post-deploy smoke test step (hit `/health`, hit Worker URL, hit static site)
- `✅ VERIFY`: LJ triggers one real deploy per target and confirms each lands correctly

---

### Phase 7 — Flutter Mobile App

**Step 7.1 — Scaffold + API client**
- `🤖 CLAUDE CODE`: Scaffold Flutter app, build API client hitting `/contact` and `/chat`
- `🤖 CLAUDE CODE`: Test: unit tests for the API client (mocked HTTP), widget tests for core screens
- `✅ VERIFY`: LJ runs the app in a simulator/emulator and confirms it loads and can reach the live backend

**Step 7.2 — On-device summarizer**
- `🤖 CLAUDE CODE`: Integrate `flutter_local_ai` with a small on-device model for on-device summarization
- `🤖 CLAUDE CODE`: Test: widget test for the summarizer UI state (loading/result/error), manual check of actual inference output
- `✅ VERIFY`: LJ triggers the summarizer on a real device/simulator and confirms it works without network access

**Step 7.3 — Analytics and crash reporting**
- `🧑 MANUAL`: Create Sentry Flutter project and PostHog project (or reuse web PostHog project as a separate environment), provide keys
- `🤖 CLAUDE CODE`: Integrate `sentry_flutter` (crash/error reporting) and `posthog_flutter` (event tracking: screen views, chat used, summarizer used)
- `🤖 CLAUDE CODE`: Test: widget test confirming events fire on key interactions (mocked SDKs); trigger a deliberate test crash manually
- `✅ VERIFY`: LJ confirms the test crash appears in Sentry and a test event appears in PostHog

**Step 7.4 — Store readiness**
- `🧑 MANUAL`: Both the Apple App Store and Google Play are in scope (decision 42) — create the Apple Developer and Google Play Developer accounts, and gather what Step 7.5's automated publishing needs: an App Store Connect API key, an Apple signing certificate + provisioning profile, and a Google Play service-account JSON + upload keystore
- `✅ VERIFY`: LJ confirms both accounts exist and the signing/publishing credentials are in hand

**Step 7.5 — Mobile CI/CD and store publishing**
- `🤖 CLAUDE CODE`: `mobile-build.yml` — Flutter test + build APK/IPA on tag (path-filtered to `mobile/**`), publishing to the Google Play internal testing track and TestFlight using Step 7.4's credentials
- `🤖 CLAUDE CODE`: Test: workflow produces a build artifact on a tag push; publishing step is dry-run against the internal/test track only, never production
- `✅ VERIFY`: LJ confirms the build lands in both the Google Play internal testing track and TestFlight

---

### Phase 8 — Monitoring & Docs

**Step 8.1 — Docs**
- `🤖 CLAUDE CODE`: Write `docs/architecture.md` (Mermaid diagram, all four inference layers explained) and `docs/decisions.md` (decision log)
- `✅ VERIFY`: LJ reads both and confirms they're accurate and readable by someone with no prior context

**Step 8.2 — Monitoring**
- `🧑 MANUAL`: Create a free UptimeRobot account (or similar), point it at `/health`
- `🤖 CLAUDE CODE`: Set up log rotation for nginx/backend on the VM
- `✅ VERIFY`: LJ confirms the uptime monitor shows a green status

---

## 5. Secrets / Environment Variables Checklist

To be stored as GitHub Actions secrets and/or VM environment variables — never committed:

- `ANTHROPIC_API_KEY`
- `ORACLE_VM_SSH_PRIVATE_KEY`
- `ORACLE_VM_HOST` (public IP or hostname)
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `SENTRY_DSN_BACKEND`, `SENTRY_DSN_WEB`, `SENTRY_DSN_MOBILE`
- `POSTHOG_API_KEY_WEB`, `POSTHOG_API_KEY_MOBILE`, `POSTHOG_HOST`
- SMTP credentials or notification webhook URL (if email notifications are used for contact form)

---

## 6. Definition of Done

- [ ] Web one-pager live at the domain, scroll animations working, contact form → triaged via Claude API → LJ notified
- [ ] "Summarize my experience" button runs entirely in-browser via WebLLM
- [ ] RAG chatbot answers questions about LJ's background using retrieved context + Claude API
- [ ] Cloudflare Workers AI pre-filters contact submissions before they reach the backend
- [ ] Flutter app builds successfully, hits the same backend, has its own on-device summarizer
- [ ] All four deploy targets (VM, Workers, static site, mobile build) deploy via GitHub Actions on the appropriate path filter
- [ ] `docs/architecture.md` and `docs/decisions.md` are complete and readable by someone with no prior context
- [ ] `/health` endpoint monitored by an external uptime check
- [ ] Sentry capturing errors from backend, web, and mobile; PostHog capturing key events from web and mobile

---

## 7. Notes for Claude Code

- Work **step by step, not phase by phase**. Each numbered step ends in a `✅ VERIFY` checkpoint — stop there and wait for LJ's explicit confirmation before starting the next step, even within the same phase.
- Every step that produces code/config includes its own tests, per the Testing Standard above — write and run them before presenting the step for verification, and report the test results alongside the verification instructions.
- Before any `🧑 MANUAL` step, stop and clearly tell LJ exactly what to do, what information to provide back, and why it can't be automated.
- If a verification fails, fix the issue and re-run the step's tests before asking LJ to verify again — don't move on with a known failure.
- Default to the tech choices in Section 2 rather than asking again, unless something is genuinely blocked (e.g. Oracle capacity issues, a package lacking ARM64 support) — in that case, propose the smallest viable substitution and note it in `docs/decisions.md`.
- Keep the VM's resource budget in mind (2 OCPU/12GB total) — the RAG vector store and embedding model should be lightweight enough to coexist with nginx and the API process comfortably.
