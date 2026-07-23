---
name: quality-gate
description: Run an orchestrator-workers review loop over the current change until it clears a defined quality bar. Use after implementing a step from docs/PROJECT_PLAN.md and before presenting it to LJ for VERIFY, before any deploy, or whenever the user asks to review, harden, or check the quality of work in this repo.
---

# Quality Gate

An orchestrator-workers loop: specialist workers review one dimension each, every finding is
adversarially refuted before it counts, confirmed findings get fixed, and the whole thing repeats
until the gate clears or the round budget runs out.

## The pattern

```
                    ┌─────────────────┐
                    │   ORCHESTRATOR  │
                    └────────┬────────┘
                             │ fan out (6 workers, parallel)
   ┌──────────┬──────────┬───┴───┬──────────┬────────────┐
correctness simplicity  scope  secrets   tests    conventions
   └──────────┴──────────┴───┬───┴──────────┴────────────┘
                             │ each finding →
                    ┌────────▼────────┐
                    │  REFUTE (worker │  default position: the finding is wrong
                    │  per finding)   │
                    └────────┬────────┘
                             │ survivors only
                    ┌────────▼────────┐
                    │      FIX        │  smallest change per finding
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │      GATE       │──── fail ──┐
                    └────────┬────────┘            │
                             │ pass                │ loop (max N rounds)
                          REPORT  ◄────────────────┘
```

**Why refutation.** A single review pass produces confident-sounding findings that don't survive
contact with the code. Each finding gets its own worker whose default position is that the
finding is wrong. Only survivors are acted on. This is the difference between a review that
improves the code and one that generates churn.

**Why one worker per dimension.** A generalist reviewer finds the obvious defect and stops. Six
narrow lenses each find what the others structurally cannot. `simplicity` is looking for excess
while `tests` is looking for absence — the same agent can't hold both postures honestly.

**Why the loop.** Fixes introduce defects. A gate that runs once is a snapshot; a gate that loops
is a guarantee.

## Quality bar

The gate clears only when **both** hold:

1. Zero confirmed findings at `blocker` or `major` severity (in `strict` mode, also `minor`).
2. The layer's test suite passes.

`secrets` findings are always `blocker` — one leaked credential compromises four deploy targets.

## Running it

The workflow spawns roughly 15–40 agents per round and costs real tokens. **Only run it when the
user has asked for it** — via this skill, or by asking for a review/quality check in this repo.

Invoke `.claude/workflows/quality-gate.js` with the Workflow tool:

```
Workflow({
  scriptPath: ".claude/workflows/quality-gate.js",
  args: {
    step: "2.3",
    scope: "backend/app/rag.py and backend/tests/test_chat.py",
    testCommand: "cd backend && pytest -v",
    maxRounds: 3,
    strict: false
  }
})
```

| Arg | Default | Meaning |
|---|---|---|
| `step` | `"unspecified"` | Plan step number — the `scope` worker uses it to detect work from future phases |
| `scope` | current working diff | What to review |
| `testCommand` | inferred from the touched directory's `CLAUDE.md` | Test suite to run |
| `maxRounds` | `3` | Round budget before it stops and reports honestly |
| `strict` | `false` | Also block on `minor` findings |

**Always pass `step` and `testCommand` when you know them.** Without `step` the scope worker
can't tell in-scope work from work that belongs to a later phase — the check that most often
catches real problems in this repo.

## Scaling it down

Full fan-out is not always warranted. Match the effort to the change:

| Change | Approach |
|---|---|
| Typo, comment, single-line config | Skip the gate. Just check it. |
| One small function, tests already green | Run one or two dimensions inline yourself — don't spawn a workflow |
| A completed plan step | Full workflow, `maxRounds: 3` |
| Anything touching secrets, deploy, or `infra/` | Full workflow, `strict: true` |
| Pre-deploy | Full workflow **plus** the `secrets-audit` skill |

## Reading the result

- `status: "pass"` — gate cleared. **Advisory findings are listed but were not fixed.** Read them;
  some are worth doing, and the loop deliberately didn't act unilaterally.
- `status: "incomplete"` — the round budget ran out. **Do not present the step for VERIFY without
  telling LJ exactly what's outstanding.** The `report` field is a blunt handover, not a summary
  to soften.
- `status: "error"` — the baseline agent failed; nothing was verified. Treat as no information,
  never as a pass.

## Rules

- **Never report a gate pass you didn't observe.** If the workflow didn't run, say it didn't run.
- **Don't re-run to get a nicer answer.** A finding that survived refutation twice is real.
- The loop can skip findings it disagrees with — that's intended, and `skipped` entries carry the
  reasoning. Read them rather than assuming everything was fixed.
- The gate is not a substitute for LJ's `✅ VERIFY`. It's what you run *before* asking.
