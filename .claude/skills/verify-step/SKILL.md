---
name: verify-step
description: Close out a numbered step from docs/PROJECT_PLAN.md - run that step's tests, report real results, and produce the VERIFY checklist for LJ. Use when finishing a plan step, when asked whether a step is done, or before moving to the next step.
---

# Verify Step

The plan's working protocol is strict and sequential. This skill is the checkout procedure for a
single numbered step. It exists because the most common failure mode on this project is drifting
forward — starting step N+1 while step N is unverified.

## The protocol

For every numbered step:

1. Implement **only** that step.
2. Run that step's tests yourself and report the result.
3. Give LJ a concrete way to verify — a command, a URL, an output to check.
4. **Stop and wait** for explicit confirmation.
5. If verification fails, fix it and repeat from 2. Never move on with a known failure.

## Procedure

### 1. Confirm scope

Re-read the step in `docs/PROJECT_PLAN.md`. State in one sentence what this step delivers, and check
the diff contains nothing else. Work belonging to a later phase is a scope violation — flag and
remove it, don't quietly keep it because it's already written.

### 2. Run the tests — actually run them

Pick the command from the touched directory's `CLAUDE.md`:

| Layer | Command |
|---|---|
| `backend/` | `cd backend && pytest -v` |
| `edge/` | `cd edge && npx vitest run` |
| `web/` | per the framework chosen in Step 3.1 |
| `mobile/` | `cd mobile && flutter test` |
| `infra/` | `shellcheck infra/setup.sh` + run it twice for idempotency |

Report the **real output**. If tests fail, say so with the failure text. If you didn't run them,
say that instead — never present an expectation as a result.

### 3. Check the step's own testing requirement

The plan attaches a specific test to most steps ("unit test asserting a known query returns the
expected chunk in top-k"). Verify *that* test exists, not merely that some suite is green.

### 4. Secrets check

If the step touched config, env handling, CI, or deploy, run the `secrets-audit` skill before
presenting anything.

### 5. Quality gate

For a substantial step, run the `quality-gate` skill first. For a trivial one, skip it and say so.

### 6. Write the VERIFY block

Present in this shape:

```markdown
## 🧪 Test results — Step X.Y

| Check | Result |
|---|---|
| <specific check> | ✅ / ❌ <real output> |

## ✅ VERIFY — Step X.Y

<Exact command to run, in a bash fence — one command, no $ prefix>

**What you should see:** <concrete expected output>

<If a 🧑 MANUAL step is next: full instructions and why it can't be automated>
```

Then **stop**. Do not begin the next step.

## Rules

- **One step at a time.** Never batch two steps because they're small.
- **A `🧑 MANUAL` step needs real instructions** — exact clicks, exact commands, what to report
  back, and *why* automation isn't possible. "Create the instance" is not instructions.
- **Give LJ something concrete to check**, not "it should work now". A command, a URL, an output.
- **Failing tests are reported, never buried.** Partial completion stated plainly beats a
  confident summary that unravels at verification.
- **Don't re-litigate a decision already made in the plan.** If something is genuinely blocked,
  propose the smallest substitution and note it for `docs/decisions.md`.
- When the step is genuinely done and verified, **say so plainly without hedging.**
