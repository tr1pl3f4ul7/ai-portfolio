/**
 * Edge pre-filter in front of the backend's /contact.
 *
 * `web form → this Worker → (spam? drop) → backend /contact → Claude triage`
 *
 * Validates cheaply before spending any inference (edge/CLAUDE.md), then
 * classifies. Spam gets a response shaped exactly like a real one — same
 * `ContactResponse` the backend returns — so nothing about the response
 * tells a spam tool it was filtered rather than delivered. Clean submissions
 * are forwarded untouched.
 */

import { classify, type Submission } from "./classify";

export interface Env {
  AI: { run(model: string, inputs: Record<string, unknown>): Promise<{ response?: string }> };
  BACKEND_URL: string;
}

const MAX_NAME_CHARS = 120; // Mirrors backend/app/config.py.
const MAX_MESSAGE_CHARS = 5000;
const LOOKS_LIKE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const JSON_HEADERS = { "content-type": "application/json" };

/**
 * Cheap rejection before any model call — missing fields, absurd lengths and
 * malformed bodies get rejected without spending inference (edge/CLAUDE.md).
 */
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
    if (request.method !== "POST") {
      return new Response(JSON.stringify({ error: "Method not allowed" }), {
        status: 405,
        headers: JSON_HEADERS,
      });
    }

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return new Response(JSON.stringify({ error: "Invalid JSON" }), { status: 400, headers: JSON_HEADERS });
    }

    const submission = validate(body);
    if (!submission) {
      return new Response(JSON.stringify({ error: "Invalid submission" }), {
        status: 400,
        headers: JSON_HEADERS,
      });
    }

    const classification = await classify(env.AI, submission);
    // The decision, never the message body — contact submissions are
    // personal data (edge/CLAUDE.md).
    console.log(`contact submission classified as ${classification}`);

    if (classification === "spam") {
      return syntheticReceipt();
    }

    return fetch(`${env.BACKEND_URL}/contact`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(submission),
    });
  },
};
