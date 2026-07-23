---
name: implement-step
description: Orchestrate implementation of a build-plan step across multiple coding subagents - survey, explore approaches, write tests first, fan out over disjoint files, integrate, then gate. Use when implementing a numbered step from docs/PROJECT_PLAN.md, or when asked to build a feature that spans more than a couple of files.
---

# Implement Step

The **coding** orchestrator. `quality-gate` reviews work that already exists; this one writes it.

## The pattern

```
SURVEY ──────────────► what does this step actually require?
   │                    (plan + layer CLAUDE.md + existing code)
   │                    open questions → STOP and ask, don't guess
   ▼
DESIGN  ┌── worker: bias SIMPLEST ──┐
(parallel)  worker: bias TESTABLE   │──► ADJUDICATE ──► work units w/
        └── worker: bias CONVENTION ┘    (pick + graft)   disjoint file ownership
   │
   ▼
CONTRACT ────────────► tests written FIRST, expected to fail
   │
   ▼
IMPLEMENT ┌── worker: unit A (owns files 1-3) ──┐
(parallel)│   worker: unit B (owns files 4-5)   │
          └── worker: unit C (owns file 6)  ────┘
   │
   ▼
INTEGRATE ───────────► fix seams, remove orphans, get the suite green
   │
   ▼
GATE ────────────────► hands off to the quality-gate workflow
```

## Why it's shaped this way

**Survey before design.** The most expensive failure on this project is building the wrong thing
or building ahead of the current step. One cheap read-only pass prevents both.

**Open questions stop the run.** If the survey finds a genuine ambiguity, the workflow returns
`needs-input` and implements nothing. That's Principle 1 enforced structurally rather than hoped
for — a workflow that guesses silently is worse than one that stops.

**Competing designs, then a judge.** Three biases — simplest, most testable, most conventional —
pull in genuinely different directions. The adjudicator picks one and grafts the best of the
others. One-shot design locks in the first idea, which is rarely the best one.

**Tests first.** Principle 4, mechanised. The contract phase writes failing tests, then
implementers make them pass. It also removes the temptation to write tests that merely describe
whatever got built.

**Disjoint file ownership.** Each implementer gets an explicit file list and is told not to touch
anything else. **The orchestrator verifies disjointness in JavaScript, not by trusting the model** —
if two units claim the same file, it collapses to a single sequential unit rather than letting two
workers corrupt each other. Silent file corruption is the one failure mode of parallel coding that
tests won't catch.

**Integration is its own phase.** Independently-written units have seams. Somebody has to own
joining them.

## Running it

```
Workflow({
  scriptPath: ".claude/workflows/build-step.js",
  args: {
    step: "2.3",
    testCommand: "cd backend && pytest -v"
  }
})
```

| Arg | Default | Meaning |
|---|---|---|
| `step` | — | Plan step number. Either this or `task` is required |
| `task` | — | Free-form description, for work outside the plan |
| `testCommand` | inferred in survey | Exact test command |
| `testFirst` | `true` | Write failing tests before implementing |
| `skipGate` | `false` | Skip the quality-gate handoff |

## When NOT to use it

This spawns 8–20 agents. Match the tool to the work:

| Work | Use |
|---|---|
| Typo, comment, rename, one-line config | Just edit it |
| Single function, single file | Write it yourself |
| A plan step touching 3+ files | This workflow |
| A step with a real design fork | This workflow — the design panel is the value |
| Trivial step in a fresh directory | Write it yourself, then `verify-step` |

Reaching for orchestration on a one-file change is exactly the over-engineering Principle 2
forbids. The workflow itself will tell you when fan-out wasn't needed — if the adjudicator returns
one unit, that was the right answer, not a failure.

## Reading the result

| `status` | Meaning |
|---|---|
| `built` | Implemented, suite green. Still needs LJ's `✅ VERIFY` |
| `built-tests-failing` | Code landed, tests are red. **Say so plainly** — do not present for VERIFY |
| `partial` | Units blocked. Report which and why |
| `needs-input` | Open questions surfaced. Put them to LJ; nothing was implemented |
| `error` | A phase died. Nothing verified — treat as no information |

Always read `blocked[]` and each unit's `deviations`. A worker that deviated from its brief had a
reason, and that reason is usually worth knowing.

## Rules

- **Never claim a step is done because the workflow returned.** Check `testsPassing` and the gate
  result, then run `verify-step`.
- The gate handoff runs `quality-gate` with `maxRounds: 2`. For anything touching secrets, deploy,
  or `infra/`, run `quality-gate` again separately with `strict: true`.
- **Don't re-run to get a better answer.** If it returned `needs-input`, answer the question.
