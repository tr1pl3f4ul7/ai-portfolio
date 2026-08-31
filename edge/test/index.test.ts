/**
 * Tests for the fetch handler: validation, routing, and the property that
 * matters most — a spam verdict never reaches the backend, and a real
 * submission is never dropped just because the model call failed.
 *
 * The Worker's `env` is a plain object built by hand rather than pulled from
 * `cloudflare:test` — `fetch(request, env)` takes it as a normal parameter,
 * so there's no need for the pool's binding-injection machinery here.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import worker, { validate, type Env } from "../src/index";

const VALID = {
  name: "Dana Okafor",
  email: "dana@example.com",
  message: "Are you available for a contract role?",
};

function fakeEnv(classification: "CLEAN" | "SPAM" = "CLEAN"): Env {
  return {
    AI: { run: async () => ({ response: classification }) },
    BACKEND_URL: "https://backend.example.test",
  };
}

function post(body: unknown): Request {
  return new Request("https://worker.example.test/contact", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("validate", () => {
  it("accepts a well-formed submission", () => {
    expect(validate(VALID)).toEqual(VALID);
  });

  it("rejects a missing field", () => {
    expect(validate({ name: "Dana", email: "dana@example.com" })).toBeNull();
  });

  it("rejects a malformed email", () => {
    expect(validate({ ...VALID, email: "not-an-email" })).toBeNull();
  });

  it("rejects a name past the backend's ceiling", () => {
    expect(validate({ ...VALID, name: "x".repeat(121) })).toBeNull();
  });

  it("rejects a message past the backend's ceiling", () => {
    expect(validate({ ...VALID, message: "x".repeat(5001) })).toBeNull();
  });

  it("rejects a non-object body", () => {
    expect(validate("just a string")).toBeNull();
    expect(validate(null)).toBeNull();
    expect(validate(42)).toBeNull();
  });
});

describe("the fetch handler", () => {
  it("rejects non-POST requests", async () => {
    const response = await worker.fetch(new Request("https://worker.example.test/contact"), fakeEnv());

    expect(response.status).toBe(405);
  });

  it("answers GET /health without touching Workers AI or the backend", async () => {
    const env = fakeEnv();
    const runSpy = vi.spyOn(env.AI, "run");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const response = await worker.fetch(new Request("https://worker.example.test/health"), env);

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "ok" });
    expect(runSpy).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("answers HEAD /health too — UptimeRobot's free monitor sends HEAD, not GET", async () => {
    const response = await worker.fetch(new Request("https://worker.example.test/health", { method: "HEAD" }), fakeEnv());

    expect(response.status).toBe(200);
  });

  it("still rejects POST /health — it's a read-only check, not a submission route", async () => {
    const response = await worker.fetch(
      new Request("https://worker.example.test/health", { method: "POST", body: "{}" }),
      fakeEnv(),
    );

    expect(response.status).toBe(405);
  });

  it("rejects malformed JSON without spending inference", async () => {
    const env = fakeEnv();
    const runSpy = vi.spyOn(env.AI, "run");
    const request = new Request("https://worker.example.test/contact", { method: "POST", body: "{not json" });

    const response = await worker.fetch(request, env);

    expect(response.status).toBe(400);
    expect(runSpy).not.toHaveBeenCalled();
  });

  it("rejects an invalid submission without spending inference", async () => {
    const env = fakeEnv();
    const runSpy = vi.spyOn(env.AI, "run");

    const response = await worker.fetch(post({ name: "", email: "x", message: "" }), env);

    expect(response.status).toBe(400);
    expect(runSpy).not.toHaveBeenCalled();
  });

  it("forwards a clean submission to the backend, untouched", async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ received: true, reference: "abc123def456" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await worker.fetch(post(VALID), fakeEnv("CLEAN"));

    expect(fetchMock).toHaveBeenCalledWith(
      "https://backend.example.test/contact",
      expect.objectContaining({ method: "POST", body: JSON.stringify(VALID) }),
    );
    expect(await response.json()).toEqual({ received: true, reference: "abc123def456" });
  });

  it("returns a real-shaped receipt for spam, without forwarding it", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const response = await worker.fetch(post(VALID), fakeEnv("SPAM"));
    const body = await response.json<{ received: boolean; reference: string }>();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(response.status).toBe(200);
    expect(body.received).toBe(true);
    // Same shape as the backend's real uuid4().hex[:12] — nothing about the
    // response should tell a spam tool it was filtered rather than delivered.
    expect(body.reference).toMatch(/^[0-9a-f]{12}$/);
  });

  it("fails open and still forwards when the model throws", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ received: true, reference: "abc" })));
    vi.stubGlobal("fetch", fetchMock);
    const env: Env = {
      AI: {
        run: async () => {
          throw new Error("model unavailable");
        },
      },
      BACKEND_URL: "https://backend.example.test",
    };

    const response = await worker.fetch(post(VALID), env);

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(response.status).toBe(200);
  });
});

describe("Turnstile", () => {
  const SECRET = "test-secret-not-real";

  /** An env with Turnstile actually configured. The default fakeEnv() has no
   * secret on purpose — that is the "not configured" path, which fails open,
   * and it is what the rest of this file exercises. */
  function guardedEnv(classification: "CLEAN" | "SPAM" = "CLEAN"): Env {
    return { ...fakeEnv(classification), TURNSTILE_SECRET_KEY: SECRET, TURNSTILE_HOSTNAMES: "ljubenvassilev.com" };
  }

  /** Routes siteverify and the backend forward to separate answers, the way
   * they are separate services in production. */
  function routedFetch(siteverify: unknown, status = 200) {
    return vi.fn(async (url: string, init?: RequestInit) => {
      void init;
      if (String(url).includes("siteverify")) {
        return new Response(JSON.stringify(siteverify), { status });
      }
      return new Response(JSON.stringify({ received: true, reference: "abc123def456" }), { status: 200 });
    });
  }

  it("rejects a submission with no token, without spending inference", async () => {
    const env = guardedEnv();
    const runSpy = vi.spyOn(env.AI, "run");
    vi.stubGlobal("fetch", routedFetch({ success: true, hostname: "ljubenvassilev.com" }));

    const response = await worker.fetch(post(VALID), env);

    expect(response.status).toBe(403);
    expect(runSpy).not.toHaveBeenCalled();
  });

  it("rejects a submission whose token siteverify refuses", async () => {
    vi.stubGlobal("fetch", routedFetch({ success: false, "error-codes": ["invalid-input-response"] }));

    const response = await worker.fetch(post({ ...VALID, turnstileToken: "bad" }), guardedEnv());

    expect(response.status).toBe(403);
  });

  it("tells a rejected human to try again rather than faking a receipt", async () => {
    // Unlike spam, which gets a synthetic receipt: the commonest cause here is
    // a token that expired in an open tab, and that person wrote a real message.
    vi.stubGlobal("fetch", routedFetch({ success: false, "error-codes": ["timeout-or-duplicate"] }));

    const response = await worker.fetch(post({ ...VALID, turnstileToken: "stale" }), guardedEnv());
    const body = await response.json<{ error?: string; received?: boolean }>();

    expect(body.received).toBeUndefined();
    expect(body.error).toMatch(/try again/i);
  });

  it("forwards a verified submission, with the token stripped", async () => {
    const fetchMock = routedFetch({ success: true, hostname: "ljubenvassilev.com" });
    vi.stubGlobal("fetch", fetchMock);

    const response = await worker.fetch(post({ ...VALID, turnstileToken: "good" }), guardedEnv("CLEAN"));

    expect(response.status).toBe(200);
    const forwarded = fetchMock.mock.calls.find(([url]) => String(url).includes("/contact"));
    expect(forwarded).toBeDefined();
    // The backend's schema has no such field and no use for the credential.
    expect(String(forwarded![1]?.body)).toBe(JSON.stringify(VALID));
  });

  it("fails open when siteverify itself is unreachable", async () => {
    // edge/CLAUDE.md's rule: a swallowed job enquiry is the failure this
    // portfolio cannot afford, and Cloudflare being down is not the sender's
    // fault. An attacker cannot choose this branch.
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes("siteverify")) throw new Error("network down");
      return new Response(JSON.stringify({ received: true, reference: "abc123def456" }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await worker.fetch(post({ ...VALID, turnstileToken: "good" }), guardedEnv());

    expect(response.status).toBe(200);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/contact"))).toBe(true);
  });

  it("still screens for spam after a token passes", async () => {
    // Turnstile proves a human sent it. It says nothing about what they wrote,
    // so the classifier must still run.
    const fetchMock = routedFetch({ success: true, hostname: "ljubenvassilev.com" });
    vi.stubGlobal("fetch", fetchMock);

    const response = await worker.fetch(post({ ...VALID, turnstileToken: "good" }), guardedEnv("SPAM"));

    expect(response.status).toBe(200);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/contact"))).toBe(false);
  });

  it("checks the token before spending inference on the submission", async () => {
    const env = guardedEnv();
    const runSpy = vi.spyOn(env.AI, "run");
    vi.stubGlobal("fetch", routedFetch({ success: false, "error-codes": ["invalid-input-response"] }));

    await worker.fetch(post({ ...VALID, turnstileToken: "bad" }), env);

    expect(runSpy).not.toHaveBeenCalled();
  });
});

describe("CORS", () => {
  const ALLOWED = "https://ljubenvassilev.com";

  function postFrom(origin: string, body: unknown = VALID): Request {
    return new Request("https://worker.example.test/contact", {
      method: "POST",
      headers: { "content-type": "application/json", Origin: origin },
      body: JSON.stringify(body),
    });
  }

  it("approves a preflight from the allowed origin", async () => {
    const request = new Request("https://worker.example.test/contact", {
      method: "OPTIONS",
      headers: {
        Origin: ALLOWED,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
      },
    });

    const response = await worker.fetch(request, fakeEnv());

    expect(response.status).toBe(204);
    expect(response.headers.get("access-control-allow-origin")).toBe(ALLOWED);
  });

  it("does not approve a preflight from an unlisted origin", async () => {
    const request = new Request("https://worker.example.test/contact", {
      method: "OPTIONS",
      headers: {
        Origin: "https://evil.example.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
      },
    });

    const response = await worker.fetch(request, fakeEnv());

    expect(response.headers.get("access-control-allow-origin")).toBeNull();
  });

  it("the spam receipt still carries the header — a preflight passing is not enough", async () => {
    const response = await worker.fetch(postFrom(ALLOWED), fakeEnv("SPAM"));

    expect(response.headers.get("access-control-allow-origin")).toBe(ALLOWED);
  });

  it("the forwarded backend response carries the header too", async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ received: true, reference: "abc123def456" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await worker.fetch(postFrom(ALLOWED), fakeEnv("CLEAN"));

    expect(response.headers.get("access-control-allow-origin")).toBe(ALLOWED);
    // Forwarding still works exactly as before — CORS wrapping must not
    // swallow the backend's real body.
    expect(await response.json()).toEqual({ received: true, reference: "abc123def456" });
  });
});
