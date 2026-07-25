/**
 * Tests for browser error tracking.
 *
 * The property that matters most: no DSN means no Sentry, full stop — the
 * default on a dev machine and in CI, so nothing here should ever call the
 * real SDK unless a key is explicitly present. `@sentry/browser` is mocked so
 * these assert on our own init logic, not Sentry's.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const init = vi.fn();
vi.mock("@sentry/browser", () => ({
  init,
  browserTracingIntegration: vi.fn(() => ({})),
}));

const { initSentry } = await import("../src/observability");

beforeEach(() => {
  init.mockClear();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("without a DSN", () => {
  it("does not initialise Sentry", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "");

    const started = await initSentry();

    expect(started).toBe(false);
    expect(init).not.toHaveBeenCalled();
  });
});

describe("with a DSN", () => {
  it("initialises Sentry with it", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "https://key@example.ingest.sentry.io/1");

    const started = await initSentry();

    expect(started).toBe(true);
    expect(init).toHaveBeenCalledOnce();
    expect(init.mock.calls[0]![0]).toMatchObject({
      dsn: "https://key@example.ingest.sentry.io/1",
    });
  });

  it("never asks Sentry to collect default PII", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "https://key@example.ingest.sentry.io/1");

    await initSentry();

    expect(init.mock.calls[0]![0]).toMatchObject({ sendDefaultPii: false });
  });

  it("extends Sentry's default integrations rather than replacing them", async () => {
    // A plain array here would silently drop the global-handler integrations
    // that catch window.onerror and unhandled rejections — the ones that do
    // the actual job of "error tracking". Only the function form keeps them.
    vi.stubEnv("VITE_SENTRY_DSN", "https://key@example.ingest.sentry.io/1");

    await initSentry();

    const { integrations } = init.mock.calls[0]![0];
    expect(typeof integrations).toBe("function");
    const defaults = [{ name: "GlobalHandlers" }];
    expect(integrations(defaults)).toEqual(expect.arrayContaining(defaults));
  });
});
