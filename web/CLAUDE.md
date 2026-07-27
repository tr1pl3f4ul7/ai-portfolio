# web/ — One-Page Portfolio Site

The **browser** inference layer, and the front door for everything else.

Three interactive pieces:
1. **On-device project finder** — "find a project" embeds the visitor's question and my real
   project entries with a small model running entirely on their device via transformers.js, then
   points at the closest match by cosine similarity. No backend call, and no generation — the
   result is always one of the real projects already on the page, never invented text (decision 44).
   If it silently falls back to a server call, the demo is a lie.
2. **Chat widget** → `POST /chat` on the backend (RAG).
3. **Contact form** → the Cloudflare Worker, which pre-filters and forwards to `/contact`.

## Stack

| Concern | Choice |
|---|---|
| Build | **Vite + vanilla TypeScript** — no component framework (decision 40) |
| Tests | **Vitest** (Vite-native) + a manual cross-browser check |
| Styling | Plain CSS using the generated tokens — see below |
| On-device model | transformers.js — all-MiniLM-L6-v2 (ONNX, embeddings only, WASM) — decisions 43, 44 |
| Errors | Sentry browser SDK |
| Analytics | PostHog JS — autocapture + explicit events |
| Deploy | GitHub Pages or Cloudflare Pages, via `web-deploy.yml` |

**Why no framework:** one page, three small interactive islands, no routing. The binding
constraint is the model download below — every kilobyte of framework JS competes with it.

## ⚠️ Never hand-edit `src/styles/tokens.css`

It is **generated** from `design/tokens.json`, which is shared with the Flutter app so both clients
stay one visual system. Edit the JSON, then:

```bash
python design/generate.py
```

Commit the source and the generated file together. Full guidance — palette logic, type roles,
motion ceiling — is in [`docs/design-system.md`](../docs/design-system.md).

**No hardcoded hex values, sizes or durations in this directory.** If a value is missing, add it to
`tokens.json`.

PostHog events to fire explicitly (beyond autocapture): **form submitted**, **chat used**,
**project finder used**.

## Rules

- **Model download is the UX problem.** Even a small model is tens of megabytes. Never start it
  on page load — require a click, show real progress, cache via the browser's model cache, and
  state the size up front.
- **Never trust an API's mere presence as proof it works.** `navigator.gpu` existed with no
  working adapter behind it in real testing, confirmed the hard way (decision 43). Check by
  actually trying the thing, not by checking that a name exists on the global.
- **Degrade honestly.** If a browser capability this page depends on is missing or broken, say so
  plainly — don't silently route to the backend instead.
- **The backend URL is configuration**, not a hardcoded literal scattered through the source.
- **Never put secrets in frontend code.** The PostHog project key and Sentry DSN are publishable
  by design; the Anthropic key is not and must never appear here. If you're reaching for
  `ANTHROPIC_API_KEY` in this directory, the design is wrong.
- **Scroll animations respect `prefers-reduced-motion`.** Non-negotiable.
- Keep the page fast without the model loaded. First paint shouldn't wait on AI anything.

## Testing

Per the plan: component/interaction tests for the form and chat widget, plus a manual
cross-browser smoke check. The project finder widget needs a **real browser** — assert on load
state and error handling in automated tests, and verify actual matching by hand (Chrome at
minimum). Document expected load time when you do.
