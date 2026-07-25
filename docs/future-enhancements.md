# Future Enhancements

Ideas worth building **after the current scope in [`PROJECT_PLAN.md`](PROJECT_PLAN.md) is
complete** — all eight phases done, deployed, and verified.

Nothing here is in scope now. The plan is built one step at a time and finishing it matters more
than widening it. These are recorded so they aren't lost, and because each one strengthens the
*existing* thesis rather than adding a second, unrelated one.

Each entry lists what must exist first, so none of them can be started early by accident.

---

## 1. RAG evaluation harness

**What:** A golden set of question/answer pairs about LJ's background, plus a scored evaluation
run over the retrieval and generation pipeline. Retrieval precision and recall at *k*, answer
groundedness, and a regression gate wired into CI so a change that degrades answer quality fails
the build.

**Why it's worth doing:** Almost every AI portfolio demonstrates that a RAG pipeline *runs*. Very
few demonstrate that its output is *measured*. "I can tell you the retrieval precision at k=4, and
CI fails if it drops" is a materially different claim from "I built a chatbot" — and evaluation is
one of the most in-demand and least commonly evidenced skills in applied AI work.

It also turns the existing chatbot from a demo into something with a quality bar, which is the
same distinction this repo already draws between code that runs and code that's verified.

**Shape:**
- `backend/eval/` — golden set as data, runner as a script
- Metrics: retrieval hit rate @k, MRR, answer groundedness (LLM-as-judge, or string-overlap for a
  cheaper deterministic signal)
- CI job on `backend/**`, failing below a recorded threshold
- Results published in `docs/` so the numbers are visible, not just claimed

**Depends on:** Phase 2 complete (`/chat` and the vector store must exist).

**Watch out for:** LLM-as-judge costs money per run and is non-deterministic — CI needs either a
cached judge, a deterministic metric, or a scheduled rather than per-push run. Decide before
wiring it into the build.

---

## 2. Cost and latency comparison across the four inference layers

**What:** Real measurements — not estimates — of what each of the four layers costs and how long
it takes, published as a table and a short written analysis.

| Layer | Cold start | Warm latency | Cost per 1k requests | Notes |
|---|---|---|---|---|
| Browser (transformers.js) | model download | on-device inference | $0 | device-dependent |
| Edge (Workers AI) | | | | |
| Server (VM RAG) | | | | |
| Cloud API (Claude) | | | | |

**Why it's worth doing:** This is the single strongest reinforcement of the project's central
claim. The repo argues that *where* inference runs is an architectural decision with real
trade-offs. Right now that argument is made in prose. With measured numbers it becomes evidence —
and it answers the obvious interview question ("why not just call the API for everything?") with
data rather than opinion.

It also surfaces genuinely interesting findings: the browser layer's cost is zero but its *first*
request costs a multi-hundred-megabyte download; the VM is free but capped by 12 GB; the edge is
fast but the model is small.

**Shape:**
- A benchmark script hitting each layer with the same representative workload
- Cold vs warm measured separately — the distinction is most of the story
- Results in `docs/architecture.md` alongside the diagram, where the argument already lives

**Depends on:** Phases 2, 3 and 4 complete (all four layers must be live).

**Watch out for:** Browser measurements vary hugely by device and network. Report the test
machine and be explicit that it's one sample, not a benchmark suite.

---

## 3. Prompt-injection testing on the contact form

**What:** A test suite of adversarial contact-form submissions designed to subvert the Claude
triage step — instruction override, role confusion, exfiltration attempts, and content crafted to
manipulate the classification or the draft reply. Assert the system holds.

**Why it's worth doing:** The contact form takes untrusted input from strangers and feeds it to an
LLM whose output LJ then reads and acts on. That is a genuine injection surface, not a theoretical
one. Demonstrating that it was identified and tested is security thinking applied specifically to
AI — timely, and rarely evidenced in a portfolio.

It also pairs naturally with the edge pre-filter already in the design: a layered defence where
the Worker screens obvious abuse and the backend is hardened against what gets through.

**Shape:**
- `backend/tests/test_injection.py` — adversarial cases as data, mocked Claude responses for the
  deterministic assertions
- Assertions on the *structure* of what triage returns: does a hostile submission still produce a
  valid classification, or can it force arbitrary output into the draft reply?
- A short write-up of the threat model in `docs/` — the reasoning is the portfolio value

**Depends on:** Phase 2.4 complete (`/contact` and the triage prompt must exist).

**Watch out for:** Keep the adversarial payloads as test fixtures, not as anything the app can
execute. And per the repo's testing standard, the Claude call stays mocked in CI — live-calling
with hostile input on every push is both costly and pointless.
