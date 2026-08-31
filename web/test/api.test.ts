/**
 * Tests for the backend client.
 *
 * `fetch` is stubbed throughout — no test in this suite touches the network.
 * What matters here is the request shape (the contract with
 * backend/app/schemas.py) and that every failure becomes a message a visitor
 * can read rather than a status code they can't.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  askQuestion,
  getAskContent,
  getBrowserContent,
  getContactContent,
  getProfile,
  getProjects,
  submitContact,
} from "../src/api";

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

describe("askQuestion", () => {
  it("posts the question as JSON to /chat", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ answer: "Yes.", sources: [] }));

    await askQuestion("Does he have security experience?");

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toContain("/chat");
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ question: "Does he have security experience?" });
  });

  it("returns the answer and its sources", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        answer: "He works at AI Talent.",
        sources: [{ document: "experience.md", section: "Software Engineer at AI Talent" }],
      }),
    );

    const response = await askQuestion("Who does he work for?");

    expect(response.answer).toBe("He works at AI Talent.");
    expect(response.sources).toEqual([
      { document: "experience.md", section: "Software Engineer at AI Talent" },
    ]);
  });
});

describe("submitContact", () => {
  it("posts every field to /contact", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ received: true, reference: "abc123" }));

    await submitContact({ name: "Dana", email: "dana@example.com", message: "Hello." }, "tok");

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toContain("/contact");
    expect(JSON.parse(init.body)).toEqual({
      name: "Dana",
      email: "dana@example.com",
      message: "Hello.",
      turnstileToken: "tok",
    });
  });

  it("sends a null token when Turnstile produced none", async () => {
    // The field is always present so the Worker can tell "no token" from "field
    // missing because an old client is calling us".
    fetchMock.mockResolvedValue(jsonResponse({ received: true, reference: "abc123" }));

    await submitContact({ name: "Dana", email: "dana@example.com", message: "Hello." });

    const [, init] = fetchMock.mock.calls[0]!;
    expect(JSON.parse(init.body).turnstileToken).toBeNull();
  });

  it("returns the reference", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ received: true, reference: "2418ab6cf5e0" }));
    await expect(submitContact({ name: "D", email: "d@e.com", message: "hi" })).resolves.toEqual({
      received: true,
      reference: "2418ab6cf5e0",
    });
  });
});

describe("content endpoints", () => {
  it("fetches profile with GET, no body", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ name: "ljuben vassilev", location: "brisbane, australia", tagline: "..." }),
    );

    const profile = await getProfile();

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toContain("/content/profile");
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
    expect(profile.name).toBe("ljuben vassilev");
  });

  it("fetches browser content from /content/browser", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ label: "browser", heading: "h", description: "d" }));

    await getBrowserContent();

    expect(fetchMock.mock.calls[0]![0]).toContain("/content/browser");
  });

  it("fetches ask content, including the suggestion chips", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ label: "ask", heading: "h", description: "d", suggestions: ["Q1?", "Q2?"] }),
    );

    const ask = await getAskContent();

    expect(fetchMock.mock.calls[0]![0]).toContain("/content/ask");
    expect(ask.suggestions).toEqual(["Q1?", "Q2?"]);
  });

  it("fetches contact content from /content/contact", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ label: "contact", heading: "h", description: "d" }));

    await getContactContent();

    expect(fetchMock.mock.calls[0]![0]).toContain("/content/contact");
  });

  it("fetches the project cards from /content/projects", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        label: "selected work",
        heading: "h",
        items: [{ company: "acme", year: "2020", name: "Widget", note: "note" }],
      }),
    );

    const projects = await getProjects();

    expect(fetchMock.mock.calls[0]![0]).toContain("/content/projects");
    expect(projects.items).toHaveLength(1);
  });

  it("a failed content fetch becomes the same readable ApiError as any other endpoint", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(getProfile()).rejects.toMatchObject({
      message: expect.stringContaining("Couldn't reach the server"),
    });
  });
});

describe("failures become readable messages", () => {
  it("explains a daily limit rather than showing 429", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "per-ip limit of 20 requests per day reached" }, { status: 429 }),
    );

    await expect(askQuestion("hi")).rejects.toMatchObject({
      status: 429,
      message: expect.stringContaining("Daily limit"),
    });
  });

  it("carries Retry-After through so the UI could use it", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "rate limited" }), {
        status: 429,
        headers: { "Content-Type": "application/json", "Retry-After": "3600" },
      }),
    );

    await expect(askQuestion("hi")).rejects.toMatchObject({ retryAfterSeconds: 3600 });
  });

  it("surfaces the backend's own detail on 503, which says what is down", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "vector store missing at /opt/.../vectors.db" }, { status: 503 }),
    );

    await expect(askQuestion("hi")).rejects.toMatchObject({
      status: 503,
      message: expect.stringContaining("vector store missing"),
    });
  });

  it("does not show raw field errors from a 422", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: [{ loc: ["body", "question"] }] }, { status: 422 }));

    const error = await askQuestion("").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).not.toContain("loc");
    expect((error as ApiError).message).toContain("check the fields");
  });

  it("reports a network failure as a connection problem", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(askQuestion("hi")).rejects.toMatchObject({
      message: expect.stringContaining("Couldn't reach the server"),
    });
  });

  it("survives an error body that is not JSON", async () => {
    fetchMock.mockResolvedValue(new Response("<html>502 Bad Gateway</html>", { status: 502 }));

    const error = await askQuestion("hi").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(502);
  });
});
