/**
 * Cloudflare Turnstile verification.
 *
 * Proves a submission came from a browser with a human behind it, before the
 * Worker spends inference on it or forwards it to the VM. No cookies, no
 * fingerprinting, no personal data — which is why this and not the obvious
 * alternatives (decision 68).
 *
 * The widget on the page is not the protection. Anything can POST straight at
 * this Worker, so the token has to be checked server-side, here. Tokens are
 * single-use: replaying one fails, which is what stops a bot harvesting a
 * single valid token and reusing it.
 *
 * ---
 *
 * Three outcomes, not two, and the third is the whole reason this file is
 * shaped the way it is.
 *
 * edge/CLAUDE.md says **fail open, not closed**: a missed spam message is an
 * annoyance, a silently swallowed job enquiry is the failure this portfolio
 * cannot afford. That rule was written about the spam classifier, and applying
 * it verbatim to Turnstile would be nonsense — a check that waves everything
 * through when it fails is not a check, and every bot would simply omit the
 * token.
 *
 * The rule survives once you separate two things it conflates:
 *
 *   `rejected`     — the *client* failed the check. No token, a malformed one,
 *                    a replayed one, or one minted for somebody else's site.
 *                    Refuse. This is the case Turnstile exists for.
 *   `unverifiable` — *we* could not run the check. Cloudflare's endpoint is
 *                    down, timed out, or answered with something unreadable.
 *                    Nothing is known about the sender, and punishing them for
 *                    our outage is exactly the swallowed-enquiry failure. The
 *                    caller forwards, and the submission still faces the spam
 *                    classifier and the backend's daily ceiling behind this.
 *
 * An attacker cannot choose `unverifiable` — it depends on Cloudflare's
 * availability, not on anything in the request.
 */

export const SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

/** Cloudflare's documented ceiling. Anything longer is not a token. */
const MAX_TOKEN_CHARS = 2048;

/** Long enough to absorb a slow response, short enough that a visitor is not
 * left waiting on an endpoint that is not coming back. */
const TIMEOUT_MS = 10_000;

export type Outcome = "human" | "rejected" | "unverifiable";

export interface VerifyResult {
  outcome: Outcome;
  /** Safe to log: describes the decision, never the submission. */
  reason: string;
}

/** Just the fields we act on. Cloudflare returns more. */
interface SiteverifyBody {
  success?: boolean;
  hostname?: string;
  "error-codes"?: string[];
}

/** Injectable so tests can exercise every branch without a network. */
export type Fetcher = (url: string, init: RequestInit) => Promise<Response>;

export async function verifyToken(
  secret: string,
  token: unknown,
  remoteIp: string | null,
  expectedHostnames: ReadonlySet<string>,
  fetchImpl: Fetcher = fetch,
): Promise<VerifyResult> {
  // "Can this check run at all?" comes before "did the client pass it?", so a
  // deployment without the secret is unverifiable rather than rejecting every
  // visitor. A missing secret is our misconfiguration, not the sender's fault,
  // and breaking the contact form because a deploy forgot a secret is the worse
  // of the two failures. The caller logs this branch distinctly, because
  // "protection silently absent" is not a state anyone should sit in unaware.
  //
  // It also means `wrangler dev` works without a secret, and that adding
  // Turnstile did not require rewriting every existing Worker test.
  if (!secret) {
    return { outcome: "unverifiable", reason: "TURNSTILE_SECRET_KEY is not set" };
  }

  // A missing token is the commonest shape of an automated submission, and it
  // costs nothing to say so without a round trip.
  if (typeof token !== "string" || token.length === 0) {
    return { outcome: "rejected", reason: "no turnstile token" };
  }
  if (token.length > MAX_TOKEN_CHARS) {
    return { outcome: "rejected", reason: "turnstile token too long" };
  }

  let response: Response;
  try {
    response = await fetchImpl(SITEVERIFY_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      signal: AbortSignal.timeout(TIMEOUT_MS),
      body: JSON.stringify({
        secret,
        response: token,
        ...(remoteIp ? { remoteip: remoteIp } : {}),
      }),
    });
  } catch {
    return { outcome: "unverifiable", reason: "siteverify unreachable" };
  }

  if (!response.ok) {
    return { outcome: "unverifiable", reason: `siteverify returned ${response.status}` };
  }

  let body: SiteverifyBody;
  try {
    body = (await response.json()) as SiteverifyBody;
  } catch {
    return { outcome: "unverifiable", reason: "siteverify returned an unreadable body" };
  }

  if (body.success !== true) {
    // Cloudflare's own codes are safe to log — they describe the token, not the
    // person or the message.
    const codes = body["error-codes"] ?? [];
    return {
      outcome: "rejected",
      reason: codes.length > 0 ? `turnstile rejected: ${codes.join(", ")}` : "turnstile rejected",
    };
  }

  // The site key is public — it is in the page source, by design. Without this
  // check, anyone could embed it on their own domain, mint valid tokens there,
  // and post them here. `hostname` is what ties a token back to our site.
  //
  // Skipped when no hostnames are configured, so local `wrangler dev` against
  // a test key still works; production sets it in wrangler.toml.
  if (expectedHostnames.size > 0 && !expectedHostnames.has(body.hostname ?? "")) {
    return { outcome: "rejected", reason: "turnstile token minted for another host" };
  }

  return { outcome: "human", reason: "verified" };
}
