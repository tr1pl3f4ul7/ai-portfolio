# docs/ — Architecture, Decisions, Runbook

For a portfolio project, **the documentation is a deliverable, not an afterthought.** A recruiter
or engineer reading this repo will judge the thinking as much as the code. These three files are
where the thinking lives.

## Files

| File | Purpose | Phase |
|---|---|---|
| `architecture.md` | Mermaid diagram + walkthrough of all four inference layers | 8.1 |
| `decisions.md` | Decision log — what was chosen, what was rejected, and why | 8.1 (append throughout) |
| `runbook.md` | Deploy, rotate secrets, restart services, recover from failure | 8.1 |

## The audience test

The plan's success criterion is that these are **"readable by someone with no prior context."**
That's the bar. Concretely:

- Expand every acronym on first use. RAG, VCN, OCPU, DSN, MLC.
- Don't assume the reader knows why on-device inference matters. Say it.
- A diagram without prose is decoration. A wall of prose without a diagram is unreadable. Both.
- No dead links, no references to files that don't exist.

## `decisions.md` — append as you go

Don't wait for Phase 8. **Whenever a real decision gets made, record it immediately** — the
reasoning is vivid now and gone in three weeks.

One entry per decision:

```markdown
## <Decision title>

**Date:** YYYY-MM-DD
**Status:** accepted | superseded by <link>

**Context:** what forced a choice.
**Decision:** what was chosen.
**Rejected:** the alternatives, and specifically why not.
**Consequences:** what this now commits us to, including the downsides.
```

**Record the rejected options honestly.** "We picked Sentry + PostHog over Firebase because each
one spans multiple layers, and a Firebase/Supabase split would be two unrelated tools with no
shared reasoning" is a far stronger signal than "we picked Sentry." The rejections are the
evidence that a decision actually happened.

Decisions already made and owed an entry:
- Sentry + PostHog over Firebase/Supabase (rationale in `docs/PROJECT_PLAN.md` §2)
- Oracle Ampere A1 as the server target
- `sqlite-vec` over a hosted vector database
- `flutter_local_ai` over bundling a model in the app
- The local ARM64 torch index workaround
- Whatever gets decided in Step 3.1 (web framework) and Step 5.2 (TLS mode)

## `runbook.md`

Written for **LJ at 2am with a broken site**, not for a reader admiring the design. Copy-pasteable
commands, no narrative. Cover: deploying each of the four targets, rotating every secret in §5 of
the plan, restarting the backend, reading logs, and what to check first when `/health` is down.

## Style

- British/Australian spelling, matching the rest of the repo.
- Present tense, active voice.
- Prefer a table over a paragraph when the content is comparative.
- Every Mermaid block must actually render — check it, don't assume.
