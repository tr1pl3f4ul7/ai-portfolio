# web/ — One-Page Portfolio Site

The **browser** inference layer, and the front door for everything else.

Three interactive pieces:
1. **WebLLM summariser** — "Summarize my experience" runs a quantised LLM entirely on the
   visitor's device. No backend call. This is the whole point of the layer; if it silently falls
   back to a server call, the demo is a lie.
2. **Chat widget** → `POST /chat` on the backend (RAG).
3. **Contact form** → the Cloudflare Worker, which pre-filters and forwards to `/contact`.

## ⚠️ Framework is NOT chosen yet

The plan says "HTML/CSS/JS (or lightweight framework)" and defers the decision to **Step 3.1**,
where LJ picks a design direction. The test tooling follows from it — "Playwright or Vitest
depending on framework chosen."

**Do not pick a framework unilaterally.** Until Step 3.1 is confirmed, this is an open decision.
Record the outcome in `docs/decisions.md` when it's made.

## What *is* fixed

| Concern | Choice |
|---|---|
| On-device model | WebLLM — Llama-3.2-1B-Instruct or Qwen2.5-0.5B-Instruct (MLC quantised) |
| Errors | Sentry browser SDK |
| Analytics | PostHog JS — autocapture + explicit events |
| Deploy | GitHub Pages or Cloudflare Pages, via `web-deploy.yml` |

PostHog events to fire explicitly (beyond autocapture): **form submitted**, **chat used**,
**summariser used**.

## Rules

- **Model download is the UX problem.** Even a small quantised model is a multi-hundred-MB
  fetch. Never start it on page load — require a click, show real progress, cache via the
  browser's model cache, and state the size up front.
- **Degrade honestly.** WebGPU isn't everywhere. If unsupported, say so plainly — don't silently
  route to the backend.
- **The backend URL is configuration**, not a hardcoded literal scattered through the source.
- **Never put secrets in frontend code.** The PostHog project key and Sentry DSN are publishable
  by design; the Anthropic key is not and must never appear here. If you're reaching for
  `ANTHROPIC_API_KEY` in this directory, the design is wrong.
- **Scroll animations respect `prefers-reduced-motion`.** Non-negotiable.
- Keep the page fast without the model loaded. First paint shouldn't wait on AI anything.

## Testing

Per the plan: component/interaction tests for the form and chat widget, plus a manual
cross-browser smoke check. The WebLLM widget needs a **real browser** — assert on load state and
error handling in automated tests, and verify actual inference by hand (Chrome at minimum).
Document expected load time when you do.
