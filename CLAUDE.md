# CLAUDE.md — AI Showcase Portfolio

Guidance for Claude Code working in this repository. Subdirectories have their own `CLAUDE.md`
with layer-specific rules; read the one for the directory you're touching.

---

## Working Principles

### 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

Touch only what you must. Clean up only your own mess.

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require
constant clarification.

### 5. The Build Plan Is the Boss

This project is built from `docs/PROJECT_PLAN.md` **one step at a time, not one phase at a time**.

- Implement only the current numbered step. Never work ahead.
- Run that step's tests yourself and report real output — not a summary of what you expect.
- Give LJ a concrete way to verify: a command to run, a URL to open, an output to check.
- **Stop and wait** for explicit confirmation before starting the next step.
- If verification fails, fix and re-run the tests before asking again. Never move on with a
  known failure.
- Don't override a decision already made in the plan without confirming first. If something is
  genuinely blocked (a Copilot PC compatibility gap, Oracle capacity), propose the *smallest*
  viable substitution and record it in `docs/decisions.md`.

Anything tagged `🧑 MANUAL` in the plan needs step-by-step instructions for LJ **and** an
explanation of why it can't be automated.

### 6. Secrets Never Enter the Repo

This project has four deploy targets and a dozen credentials. The blast radius of one leaked key
is the whole stack.

- Never hardcode a secret, never paste one into a commit, never echo one into terminal output.
- Secrets live in: a gitignored `.env` locally, GitHub Actions secrets in CI, and environment
  variables on the VM. Nowhere else.
- Reference `.env.example` with dummy values for the shape; never the real thing.
- Before any commit that touches config, check nothing sensitive is staged.
- If you ever find a secret already committed, say so immediately and loudly — rotation is
  required, deleting the file is not enough.

The canonical list of required secrets is Section 5 of `docs/PROJECT_PLAN.md`.

### 7. Conventional Commits, Always

Every commit message uses `<type>[(scope)]: <description>`.

- Types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `ci`, `perf`, `build`.
- Scopes match top-level directories: `backend`, `web`, `edge`, `mobile`, `infra`, `docs`, `ci`.
- Imperative mood, lowercase description, no trailing period.
- Body explains *why*, not *what* — the diff already says what.

```
feat(backend): add /chat RAG endpoint

Retrieval runs against the local sqlite-vec store before the Claude call so the
prompt carries grounded context. Top-k is 4, chosen to stay inside the VM's
memory budget alongside the embedding model.
```

Commit or push **only when asked**.

### 8. Prove It Works

Never report success you haven't observed.

- Ran the tests? Show the output. Didn't run them? Say so.
- Some tests failed? State it plainly with the failure, don't bury it.
- Skipped a step? Say which and why.
- "Should work" is not a result. Neither is a green checkmark you didn't earn.

When it genuinely is done and verified, say so plainly without hedging.

---

## What This Project Is

A portfolio site that deliberately runs inference in **four different places**, because the
architectural reasoning is the actual content:

| Layer | Runs on | Does |
|---|---|---|
| **Browser** | Visitor's device | On-device model (transformers.js) matches a question to LJ's real projects — no network, no API cost |
| **Edge** | Cloudflare Workers AI | Spam/quality pre-filter on contact submissions |
| **Server** | Oracle Ampere A1 VM (2 OCPU / 12 GB) | FastAPI RAG chatbot over a local vector store |
| **Cloud API** | Anthropic Claude API | Contact triage + RAG answer generation |

Plus a Flutter app reusing the same backend with platform-native on-device summarisation.

**Design consequence:** the VM has 12 GB total for nginx + FastAPI + the embedding model + the
vector store. Keep the server side lightweight. If a change meaningfully increases memory
footprint, flag it.

---

## Repo Map

| Path | What lives there | Owning phase |
|---|---|---|
| `web/` | One-pager: animations, chat widget, on-device project finder | 3 |
| `mobile/` | Flutter app | 6 |
| `backend/` | FastAPI: RAG chatbot + contact triage | 2 |
| `edge/` | Cloudflare Worker pre-filter | 4 |
| `infra/` | `setup.sh`, nginx config, systemd units | 1 |
| `design/` | `tokens.json` — the visual contract shared by `web/` and `mobile/` | 3 |
| `docs/` | architecture, decision log, runbook, design system | 8 |
| `.github/workflows/` | Path-filtered CI/CD to four targets | 7 |

**`design/tokens.json` is generated into both clients.** Never hand-edit
`web/src/styles/tokens.css` or `mobile/lib/theme/tokens.dart` — edit the JSON and run
`python design/generate.py`. See `docs/design-system.md`.

Empty directories currently hold `.gitkeep`. Real contents arrive in the owning phase — **don't
pre-create files for a phase you haven't reached.**

---

## Environment — Read This Before Installing Anything

The dev machine is a **Copilot PC** (Arm-based Windows). This is not a normal x64 box and it bites
in specific places:

- **`pip install torch` fails.** PyPI has zero `win_arm64` wheels. They exist only at
  `https://download.pytorch.org/whl/cpu`, which `backend/requirements.txt` declares as an extra
  index. This matters because `sentence-transformers/all-MiniLM-L6-v2` depends on torch.
- **That index is used on *every* platform, not just here.** PyPI's default Linux torch pulls in
  the whole CUDA toolkit — several GB of `nvidia-*` packages. Nothing in this project has a GPU.
  `torch==2.13.0+cpu` publishes wheels for `win_arm64`, `manylinux_2_28_aarch64` (VM, container)
  and `manylinux_2_28_x86_64` (CI), so one pin covers every target.
- **`sqlite-vec` has no Windows-on-Arm wheel at all.** Backend retrieval tests run in a Linux
  container: `cd backend/test && ./run-tests.sh`. A native `pytest` skips them.
- **Flutter has no native Windows-on-Arm build.** The x64 SDK runs under emulation. Works, just
  slower.
- **`workerd` (what `wrangler` and the edge Worker's test pool both run on) has no Windows-on-Arm
  build at all** — `npm install` in `edge/` fails outright, not just at test time. Edge tests run
  in a Linux container the same way: `cd edge/test && ./run-tests.sh`.
- Shell is PowerShell 7+; a Bash tool is also available. They take different syntax.

Installed toolchain: Python 3.12.10 (**use this**; 3.11.9 also present but `backend/` targets
3.12 to match the VM and CI), Node 24.18.0, npm 11.16.0, gh 2.96.0, Flutter 3.44.7,
Android Studio + SDK 36.1.0 + JDK 21, shellcheck 0.11.0, Docker Desktop 4.83.0 with MCP
Toolkit 0.43.1.

---

## Testing Standard by Layer

Every step that produces code or config carries its own tests. Write and run them **before**
presenting the step for verification, and report the results alongside.

| Layer | Unit | Integration | Notes |
|---|---|---|---|
| `backend/` | `pytest` for logic (classification parsing, retrieval ranking) | `TestClient`/`httpx` for endpoints | **Claude API calls are mocked in CI** — never live-call in automated tests |
| `edge/` | `vitest` + `@cloudflare/vitest-pool-workers` | local `wrangler dev` smoke test | Run before every deploy |
| `web/` | component/interaction tests | manual cross-browser check | Project finder widget needs a real browser |
| `mobile/` | widget tests, API client unit tests | `flutter test` in CI | |
| `infra/` | `shellcheck` + idempotency (run twice, no errors, no dupes) | `/health` smoke test after every deploy | |

---

## Line Endings

`.gitattributes` pins LF for `infra/**` and `*.sh`. Don't override it. A CRLF shell script
lands on Ubuntu and dies at the shebang with a `bad interpreter` error that reads like a typo.

---

## Available Tooling

Skills in `.claude/skills/` — invoke with `/<name>`:

**Writing code**

| Skill | Use when |
|---|---|
| `implement-step` | Building a plan step that spans 3+ files — orchestrates coding across subagents |
| `write-tests` | Adding tests — per-layer conventions and the bar a test must clear |
| `api-contract` | Touching `backend/app/schemas.py` or any endpoint — keeps the three clients in sync |

**Checking work**

| Skill | Use when |
|---|---|
| `quality-gate` | Before presenting non-trivial work — orchestrator-workers review loop |
| `secrets-audit` | Before any commit touching config, and before every deploy |
| `verify-step` | Finishing a plan step — runs tests, drafts the VERIFY checklist |

Two multi-agent workflows sit behind these:

- `.claude/workflows/build-step.js` — the **coding** orchestrator. Survey → competing designs →
  tests first → parallel implementers over disjoint files → integrate → gate.
- `.claude/workflows/quality-gate.js` — the **review** orchestrator. Six specialist reviewers →
  adversarial refutation → fix → re-gate, looping until clean.

`build-step` hands off to `quality-gate` when it finishes.

Both spawn many agents and cost real tokens. **They run only when explicitly invoked**, and
neither is a substitute for LJ's `✅ VERIFY`. Don't reach for orchestration on a one-file change —
that's the over-engineering Principle 2 forbids.

---

## MCP First

**Before reaching for a CLI, check whether an MCP server can do the job.** Fall back to the CLI
only when none can — and say which it was and why.

Servers are managed through Docker's MCP Toolkit (ships with Docker Desktop). The local profile is
`ai_portfolio`. `.mcp.json` is gitignored because it hardcodes machine-specific paths; recreate it
with:

```
docker mcp profile create --name "ai-portfolio" --server "catalog://mcp/docker-mcp-catalog/github-official"
docker mcp client connect --profile ai_portfolio claude-code
docker mcp oauth authorize github
```

| Service | Status | Notes |
|---|---|---|
| GitHub | connected | `github-official`, OAuth — prefer over the `gh` CLI |
| Sentry | not yet | Connect at Step 2.5 |
| Cloudflare | not yet | Several servers; connect at Phase 4 |
| Flutter/Dart | not yet | Connect at Phase 7 |
| **Docker** | **no server exists** | The catalog has no daemon-control server — `docker-docs` and `dockerhub` only. `docker mcp` is a *gateway* for running other servers, not a way to drive Docker. `infra/test/` uses the CLI, and needs `--privileged`, `--cgroupns=host` and `docker cp`, which no community server exposes |
| **Oracle Cloud** | **none official** | Not in the catalog. Community OCI servers exist but would hold control-plane credentials for the tenancy — not worth the blast radius (Principle 6) |

Discover what exists: `docker mcp catalog show mcp/docker-mcp-catalog:latest` (314 servers).
