/**
 * Edge pre-filter in front of the backend's /contact.
 *
 * `web form → this Worker → (bot? reject) → (spam? drop) → backend /contact → triage`
 *
 * Three gates, deliberately ordered cheapest-first: local validation costs
 * nothing, Turnstile costs a fast network round trip, and the spam classifier
 * costs inference. Nothing expensive runs behind something cheap that would
 * have rejected the request anyway (edge/CLAUDE.md).
 *
 * The two rejections behave differently on purpose:
 *
 * - **Spam** gets a response shaped exactly like a real one — same
 *   `ContactResponse` the backend returns — so nothing tells a spam tool it
 *   was filtered rather than delivered.
 * - **A failed Turnstile check** gets an honest 403. It has to: the commonest
 *   real-world cause is a token that expired while someone had the tab open,
 *   and a human who typed a genuine enquiry needs to be told to try again
 *   rather than handed a fake receipt for a message nobody will ever read.
 */

import { classify, type Submission } from "./classify";
import { verifyToken } from "./turnstile";

export interface Env {
  AI: { run(model: string, inputs: Record<string, unknown>): Promise<{ response?: string }> };
  BACKEND_URL: string;
  /** Set with `wrangler secret put TURNSTILE_SECRET_KEY`. Never in wrangler.toml. */
  TURNSTILE_SECRET_KEY?: string;
  /** Comma-separated hostnames a token may be minted for. See turnstile.ts. */
  TURNSTILE_HOSTNAMES?: string;
}

const MAX_NAME_CHARS = 120; // Mirrors backend/app/config.py.
const MAX_MESSAGE_CHARS = 5000;
const LOOKS_LIKE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const JSON_HEADERS = { "content-type": "application/json" };

// The web frontend calls this Worker from a different origin in production
// (ljubenvassilev.com vs contact.ljubenvassilev.com — decision 48's domain
// split). Without this, every browser fetch() fails with a generic "Failed
// to fetch" the browser never explains further, even though curl (which
// doesn't enforce CORS) works fine — mirrors backend/app/config.py's
// ALLOWED_ORIGINS, same reasoning, same two origins.
const ALLOWED_ORIGINS = new Set(["https://ljubenvassilev.com", "https://www.ljubenvassilev.com"]);

function corsHeaders(origin: string | null): Record<string, string> {
  if (!origin || !ALLOWED_ORIGINS.has(origin)) return {};
  return { "access-control-allow-origin": origin, vary: "Origin" };
}

/** Re-wraps a response with CORS headers merged in — used for every return
 * path, including the one forwarded verbatim from the backend. */
function withCors(response: Response, origin: string | null): Response {
  const headers = new Headers(response.headers);
  for (const [key, value] of Object.entries(corsHeaders(origin))) headers.set(key, value);
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

/**
 * Cheap rejection before any model call — missing fields, absurd lengths and
 * malformed bodies get rejected without spending inference (edge/CLAUDE.md).
 */
/** The field the web client puts the Turnstile token in.
 *
 * Read and discarded here — it is never forwarded, so `backend/app/schemas.py`
 * stays unchanged and the backend never sees a credential it has no use for. */
export const TOKEN_FIELD = "turnstileToken";

export function validate(body: unknown): Submission | null {
  if (typeof body !== "object" || body === null) return null;
  const { name, email, message } = body as Record<string, unknown>;

  if (typeof name !== "string" || name.length < 1 || name.length > MAX_NAME_CHARS) return null;
  if (typeof email !== "string" || !LOOKS_LIKE_EMAIL.test(email)) return null;
  if (typeof message !== "string" || message.length < 1 || message.length > MAX_MESSAGE_CHARS) return null;

  return { name, email, message };
}

/** A response shaped like a real ContactResponse, for a submission never sent on. */
function syntheticReceipt(): Response {
  const reference = crypto.randomUUID().replace(/-/g, "").slice(0, 12);
  return new Response(JSON.stringify({ received: true, reference }), {
    status: 200,
    headers: JSON_HEADERS,
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Dependency-free, ahead of everything else below: no CORS check, no
    // Workers AI call, no forward to the backend. Mirrors backend/app/main.py's
    // /health exactly, and exists for the same reason — an external uptime
    // monitor needs something to check that isn't "was a real submission just
    // classified." GET and HEAD both work; UptimeRobot's free HTTP(s) monitor
    // sends HEAD by default (see decision 65 / the backend/app/main.py fix
    // this mirrors) — checked explicitly rather than assumed.
    //
    // Handles its own method rejection rather than falling through: nothing
    // else in this Worker checks the path, only the method, so a POST here
    // would otherwise be parsed as an attempted contact submission and
    // rejected with a confusing 400 "Invalid submission" instead of a plain
    // 405 — caught by a test expecting the latter, not a hypothetical.
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      if (request.method === "GET" || request.method === "HEAD") {
        return new Response(JSON.stringify({ status: "ok" }), { status: 200, headers: JSON_HEADERS });
      }
      return new Response(JSON.stringify({ error: "Method not allowed" }), { status: 405, headers: JSON_HEADERS });
    }

    const origin = request.headers.get("Origin");

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          ...corsHeaders(origin),
          "access-control-allow-methods": "POST",
          "access-control-allow-headers": "content-type",
        },
      });
    }

    if (request.method !== "POST") {
      return withCors(
        new Response(JSON.stringify({ error: "Method not allowed" }), { status: 405, headers: JSON_HEADERS }),
        origin,
      );
    }

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return withCors(
        new Response(JSON.stringify({ error: "Invalid JSON" }), { status: 400, headers: JSON_HEADERS }),
        origin,
      );
    }

    const submission = validate(body);
    if (!submission) {
      return withCors(
        new Response(JSON.stringify({ error: "Invalid submission" }), { status: 400, headers: JSON_HEADERS }),
        origin,
      );
    }

    // Between local validation and inference: a round trip, but a free and
    // fast one, and it rejects the automated traffic that would otherwise be
    // the thing spending neurons.
    const hostnames = new Set(
      (env.TURNSTILE_HOSTNAMES ?? "")
        .split(",")
        .map((hostname) => hostname.trim())
        .filter(Boolean),
    );
    const verdict = await verifyToken(
      env.TURNSTILE_SECRET_KEY ?? "",
      (body as Record<string, unknown>)[TOKEN_FIELD],
      request.headers.get("CF-Connecting-IP"),
      hostnames,
    );

    if (verdict.outcome === "rejected") {
      // The reason, never the submission — same rule as the classifier below.
      console.log(`contact submission failed turnstile: ${verdict.reason}`);
      return withCors(
        new Response(
          JSON.stringify({ error: "Verification failed. Reload the page and try again." }),
          { status: 403, headers: JSON_HEADERS },
        ),
        origin,
      );
    }

    if (verdict.outcome === "unverifiable") {
      // Fails open, per edge/CLAUDE.md — but loudly. This branch means the
      // form is unprotected right now, which is a thing to find in the logs
      // rather than discover from a flood of submissions.
      console.error(`turnstile check could not run, forwarding anyway: ${verdict.reason}`);
    }

    const classification = await classify(env.AI, submission);
    // The decision, never the message body — contact submissions are
    // personal data (edge/CLAUDE.md).
    console.log(`contact submission classified as ${classification}`);

    if (classification === "spam") {
      return withCors(syntheticReceipt(), origin);
    }

    const forwarded = await fetch(`${env.BACKEND_URL}/contact`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(submission),
    });
    return withCors(forwarded, origin);
  },
};
