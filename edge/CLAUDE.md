# edge/ — Cloudflare Worker Pre-Filter

The **edge** inference layer. Sits in front of the backend's `/contact` endpoint. Verifies a
Cloudflare Turnstile token, then runs a small Workers AI model to flag spam and low-quality
submissions before they reach the VM.

Flow: `web form → Worker → (bot? reject) → (spam? drop) → backend /contact → triage`

Three gates, ordered cheapest-first: local validation is free, Turnstile is a fast network round
trip, the classifier costs inference. Nothing expensive runs behind something cheap that would
have rejected the request anyway.

## Stack

| Concern | Choice |
|---|---|
| Runtime | Cloudflare Workers |
| Model | Workers AI, `@cf/meta/llama-3.1-8b-fast-v2` (decision 46) |
| Language | TypeScript |
| Tooling | `wrangler` |
| Tests | `vitest` + `@cloudflare/vitest-pool-workers` |

## Intended layout

```
edge/
├── src/index.ts        # fetch handler: parse → classify → drop or forward
├── wrangler.toml       # AI binding, routes, vars (NO secrets in here)
├── vitest.config.ts
└── test/
```

## Rules

- **Classification logic stays pure and separately testable.** Keep the decision function apart
  from the `fetch` handler so `vitest` can exercise it without a Workers runtime. This is the
  bulk of the test value.
- **Fail open, not closed.** If Workers AI errors or times out, forward the submission rather
  than dropping it. A missed spam message is an annoyance; a silently swallowed job enquiry is
  the actual failure mode this portfolio can't afford.

  **Turnstile does not get a blanket exemption from this, and it does not get to ignore it
  either.** A security check that waves everything through when it fails is not a check — every
  bot would simply omit the token. The rule survives by splitting two things it conflates
  (`src/turnstile.ts`):

  - *The client failed the check* — no token, malformed, replayed, or minted for another site.
    **Reject.** This is what Turnstile is for.
  - *We could not run the check* — siteverify unreachable, timed out, or unreadable; or the
    secret is not configured. **Forward, and log loudly.** Nothing is known about the sender, and
    punishing them for a Cloudflare outage is exactly the swallowed-enquiry failure. An attacker
    cannot choose this branch, and the spam classifier plus the backend's daily ceiling are still
    behind it.

- **A rejected bot and a spam submission get different responses, deliberately.** Spam gets a
  synthetic receipt so a spam tool cannot tell it was filtered. A failed Turnstile check gets an
  honest 403, because its commonest real cause is a token that expired in an open tab — that
  person wrote a genuine message and needs to be told to retry, not handed a fake receipt.

- **Never forward the Turnstile token to the backend.** The Worker reads it, verifies it, and
  drops it. `backend/app/schemas.py` has no such field and no use for the credential.
- **Never put secrets in `wrangler.toml`.** It's committed. Use `wrangler secret put` for
  sensitive values and `.dev.vars` (gitignored) for local development. `TURNSTILE_SECRET_KEY` is
  the one secret this Worker has; `TURNSTILE_HOSTNAMES` next to it is not a secret and belongs in
  the toml, because it is what stops a token minted elsewhere with our public site key from being
  accepted here.
- **Validate the payload before spending inference on it.** Missing fields, absurd lengths, and
  malformed bodies get rejected cheaply — no model call needed.
- **Log the classification decision, never the message body.** Contact submissions are personal
  data.
- The model is small and will be wrong sometimes. Bias thresholds toward forwarding.

## Commands

```bash
npm install
npx vitest run
npx wrangler dev
npx wrangler deploy
```

⚠️ **None of the above runs natively here** — `workerd` has no build matching the local
environment, so even `npm install` fails. Use the container wrapper instead:

```bash
cd edge/test && ./run-tests.sh
```

It runs **the same checks as `edge-ci.yml`, in the same order**: `npm run typecheck` then `vitest`.
The typecheck is not redundant with the tests — vitest transpiles TypeScript without checking it,
so the suite cannot catch a type error at all.

Run `wrangler dev` with both a clean and an obviously-spam payload before every deploy — that
local smoke test is required by the plan, not optional. Note that a Turnstile token minted for
`localhost` is rejected with error `110200` unless you add that hostname to the widget in the
Cloudflare dashboard, so `wrangler dev` exercises the `unverifiable` path by default.
