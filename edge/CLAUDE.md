# edge/ — Cloudflare Worker Pre-Filter

The **edge** inference layer. Sits in front of the backend's `/contact` endpoint and runs a small
Workers AI model to flag spam and low-quality submissions before they cost a Claude API call or
reach the VM.

Flow: `web form → Worker → (spam? drop) → backend /contact → Claude triage`

## Stack

| Concern | Choice |
|---|---|
| Runtime | Cloudflare Workers |
| Model | Workers AI, `@cf/meta/llama-3.2-1b-instruct` |
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
- **Never put secrets in `wrangler.toml`.** It's committed. Use `wrangler secret put` for
  sensitive values and `.dev.vars` (gitignored) for local development.
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

Run `wrangler dev` with both a clean and an obviously-spam payload before every deploy — that
local smoke test is required by the plan, not optional.
