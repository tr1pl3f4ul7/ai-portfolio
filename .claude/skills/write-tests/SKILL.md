---
name: write-tests
description: Write tests for this repo following the per-layer testing standard - pytest for backend, vitest for the Cloudflare Worker, flutter test for mobile, shellcheck plus idempotency for infra. Use when adding tests, when a step needs its test coverage, or when asked to test something.
---

# Write Tests

Every step that produces code carries its own tests, and they get written and run **before** the
step is presented for verification. This skill is the per-layer how.

## Test first, where you can

Principle 4: turn the task into a verifiable goal.

- "Add validation" → write tests for invalid inputs, then make them pass.
- "Fix the bug" → write a test that reproduces it, watch it fail, then fix it.
- "Refactor X" → green before, green after, no test changes in between.

A test written after the implementation tends to describe what the code does. A test written
before describes what it *should* do. Only the second kind catches anything.

## The bar

A test earns its place only if it can fail for a real reason.

- **Assert behaviour, not implementation.** Testing that a private helper was called is testing
  your own code structure back at yourself.
- **The deletion check:** if the feature were deleted and the test still passed, the test is
  worthless.
- **Cover the failure paths.** Happy-path-only suites are where this project's real risks hide —
  API timeouts, malformed payloads, unavailable on-device models.
- **No test that needs network access** to pass in CI.

## By layer

### `backend/` — pytest

```bash
cd backend && pytest -v
```

- Endpoints via `TestClient`; pure logic (chunking, retrieval ranking, classification parsing)
  as plain unit tests.
- **The Claude API is always mocked. Never live-call it in an automated test.** CI runs on every
  push — a live call costs money per commit and flakes when the API is slow. One manual smoke
  test against the real API is fine; run it by hand, keep it out of the suite.
- Mock at the client boundary, and assert on **prompt construction** and **response parsing**
  separately. Those are the two places RAG actually breaks.
- Test the malformed cases explicitly: Claude returning non-JSON, missing fields, an empty
  retrieval result, a query longer than the context window.
- `/health` gets a test asserting it returns 200 **without** touching Claude or the vector store.

### `edge/` — vitest

```bash
cd edge && npx vitest run
```

- Keep classification logic in a pure function, separate from the `fetch` handler. That function
  is where the test value is; it needs no Workers runtime.
- Use `@cloudflare/vitest-pool-workers` for anything genuinely runtime-dependent.
- **Test the fail-open path explicitly.** If Workers AI throws or times out, the submission must
  still be forwarded. This is the single most important test in the directory — a silently
  swallowed job enquiry is the failure this project can't afford.
- Cover: clean submission, obvious spam, empty body, missing fields, oversized payload, AI error.

### `web/`

Framework isn't chosen until Step 3.1, so the runner isn't either — Vitest or Playwright follows
from that decision.

- Test form validation and submit wiring, and chat widget request/response handling.
- For the on-device project finder, automated tests cover **state transitions** — idle → loading →
  ready → error — and the ranking logic itself: given a query embedding and known project vectors,
  the closer one wins. Actual matching is verified manually in a real browser; document the load
  time when you do.
- Assert the model download never starts without an explicit click.

### `mobile/` — flutter test

```bash
cd mobile && flutter test
```

- Widget tests for the summariser's three states: loading, result, error.
- Unit tests for the API client against mocked HTTP, asserting it matches
  `backend/app/schemas.py`.
- Test the **on-device-AI-unavailable** path. Plenty of real devices lack Gemini Nano or Apple
  Foundation Models, and the app must degrade honestly rather than silently hitting the network.
- Mock Sentry and PostHog so tests emit no real events.

### `infra/` — shellcheck + idempotency

```bash
shellcheck infra/setup.sh
```

Idempotency is a hard requirement, and the test is behavioural: run the script twice on a clean
VM and assert the second run produces no errors and no duplicated config lines. Guard every
append, user creation, and symlink.

## Rules

- **Run the tests and report the real output.** Never present an expectation as a result.
- **Never weaken a test to get green.** If a test is wrong, say so explicitly and explain why —
  don't quietly change the assertion.
- **Never delete a failing test** to unblock yourself.
- Fixtures never contain real credentials — not even expired ones.
- Test names state the behaviour: `test_health_returns_200_without_vector_store`, not `test_health_2`.
