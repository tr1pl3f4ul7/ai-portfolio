/**
 * Unit tests for Turnstile verification.
 *
 * `fetch` is injected, so every branch runs without a network — including the
 * ones that matter most and are hardest to reproduce live: Cloudflare being
 * unreachable, and a token minted for somebody else's site.
 *
 * The distinction these exist to protect is `rejected` vs `unverifiable`. It is
 * the whole reason edge/CLAUDE.md's fail-open rule can apply to a security
 * check without making it meaningless, so a change that collapsed the two
 * would be a silent hole rather than a visible bug.
 */

import { describe, expect, it } from "vitest";
import { SITEVERIFY_URL, verifyToken, type Fetcher } from "../src/turnstile";

const SECRET = "test-secret-not-real";
const HOSTS = new Set(["ljubenvassilev.com"]);

function respondsWith(body: unknown, status = 200): Fetcher {
  return async () => new Response(JSON.stringify(body), { status });
}

const ACCEPTS: Fetcher = respondsWith({ success: true, hostname: "ljubenvassilev.com" });

describe("verifyToken — the client failed the check", () => {
  it("rejects a missing token without calling siteverify", async () => {
    let called = false;
    const fetcher: Fetcher = async () => {
      called = true;
      return new Response("{}");
    };

    const result = await verifyToken(SECRET, undefined, null, HOSTS, fetcher);

    expect(result.outcome).toBe("rejected");
    expect(called).toBe(false);
  });

  it("rejects an empty token", async () => {
    expect((await verifyToken(SECRET, "", null, HOSTS, ACCEPTS)).outcome).toBe("rejected");
  });

  it("rejects a non-string token", async () => {
    expect((await verifyToken(SECRET, { nope: 1 }, null, HOSTS, ACCEPTS)).outcome).toBe("rejected");
  });

  it("rejects an absurdly long token rather than posting it", async () => {
    const result = await verifyToken(SECRET, "a".repeat(2049), null, HOSTS, ACCEPTS);
    expect(result.outcome).toBe("rejected");
  });

  it("rejects when siteverify says the token is not valid", async () => {
    const fetcher = respondsWith({ success: false, "error-codes": ["invalid-input-response"] });
    const result = await verifyToken(SECRET, "tok", null, HOSTS, fetcher);

    expect(result.outcome).toBe("rejected");
    expect(result.reason).toContain("invalid-input-response");
  });

  it("rejects a replayed token", async () => {
    // Cloudflare's code for a token used twice. Single-use is what stops a bot
    // harvesting one valid token and reusing it forever.
    const fetcher = respondsWith({ success: false, "error-codes": ["timeout-or-duplicate"] });
    expect((await verifyToken(SECRET, "tok", null, HOSTS, fetcher)).outcome).toBe("rejected");
  });

  it("rejects a token minted for another host", async () => {
    // The site key is public. Without this check, anyone could embed it on
    // their own domain and post the resulting tokens here.
    const fetcher = respondsWith({ success: true, hostname: "not-lj.example" });
    const result = await verifyToken(SECRET, "tok", null, HOSTS, fetcher);

    expect(result.outcome).toBe("rejected");
    expect(result.reason).toContain("another host");
  });
});

describe("verifyToken — we could not run the check", () => {
  it("is unverifiable, not rejected, when siteverify is unreachable", async () => {
    const fetcher: Fetcher = async () => {
      throw new Error("network down");
    };
    expect((await verifyToken(SECRET, "tok", null, HOSTS, fetcher)).outcome).toBe("unverifiable");
  });

  it("is unverifiable when siteverify returns a server error", async () => {
    const result = await verifyToken(SECRET, "tok", null, HOSTS, respondsWith({}, 502));
    expect(result.outcome).toBe("unverifiable");
    expect(result.reason).toContain("502");
  });

  it("is unverifiable when siteverify returns something unreadable", async () => {
    const fetcher: Fetcher = async () => new Response("<html>nope</html>", { status: 200 });
    expect((await verifyToken(SECRET, "tok", null, HOSTS, fetcher)).outcome).toBe("unverifiable");
  });

  it("is unverifiable when the secret is not configured", async () => {
    // Our misconfiguration, not the sender's fault. Breaking the contact form
    // because a deploy forgot a secret is the worse of the two failures.
    const result = await verifyToken("", "tok", null, HOSTS, ACCEPTS);
    expect(result.outcome).toBe("unverifiable");
    expect(result.reason).toContain("TURNSTILE_SECRET_KEY");
  });
});

describe("verifyToken — the happy path", () => {
  it("accepts a valid token from an expected host", async () => {
    expect((await verifyToken(SECRET, "tok", null, HOSTS, ACCEPTS)).outcome).toBe("human");
  });

  it("skips the hostname check when none are configured", async () => {
    // So `wrangler dev` against a test key still works locally.
    const fetcher = respondsWith({ success: true, hostname: "localhost" });
    const result = await verifyToken(SECRET, "tok", null, new Set(), fetcher);
    expect(result.outcome).toBe("human");
  });

  it("posts the secret, the token and the caller's IP to siteverify", async () => {
    let seenUrl = "";
    let seenBody: Record<string, unknown> = {};
    const fetcher: Fetcher = async (url, init) => {
      seenUrl = url;
      seenBody = JSON.parse(String(init.body)) as Record<string, unknown>;
      return new Response(JSON.stringify({ success: true, hostname: "ljubenvassilev.com" }));
    };

    await verifyToken(SECRET, "tok", "203.0.113.7", HOSTS, fetcher);

    expect(seenUrl).toBe(SITEVERIFY_URL);
    expect(seenBody).toMatchObject({ secret: SECRET, response: "tok", remoteip: "203.0.113.7" });
  });

  it("omits remoteip when there is no client IP", async () => {
    let seenBody: Record<string, unknown> = {};
    const fetcher: Fetcher = async (_url, init) => {
      seenBody = JSON.parse(String(init.body)) as Record<string, unknown>;
      return new Response(JSON.stringify({ success: true, hostname: "ljubenvassilev.com" }));
    };

    await verifyToken(SECRET, "tok", null, HOSTS, fetcher);

    expect(seenBody).not.toHaveProperty("remoteip");
  });

  it("never puts the submission anywhere near siteverify", async () => {
    // Only the token and the secret leave. A contact message is personal data
    // and has no business being posted to a verification endpoint.
    let seenBody: Record<string, unknown> = {};
    const fetcher: Fetcher = async (_url, init) => {
      seenBody = JSON.parse(String(init.body)) as Record<string, unknown>;
      return new Response(JSON.stringify({ success: true, hostname: "ljubenvassilev.com" }));
    };

    await verifyToken(SECRET, "tok", null, HOSTS, fetcher);

    expect(Object.keys(seenBody).sort()).toEqual(["response", "secret"]);
  });
});
