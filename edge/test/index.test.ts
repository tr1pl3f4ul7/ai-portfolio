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
