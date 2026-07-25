/**
 * Tests for product analytics.
 *
 * The property that matters most: no key means no PostHog, full stop — the
 * default on a dev machine and in CI. `posthog-js` is mocked so these assert
 * on our own init/track logic, not PostHog's.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const init = vi.fn();
const capture = vi.fn();
vi.mock("posthog-js", () => ({
  default: { init, capture },
}));

const { initAnalytics, track } = await import("../src/analytics");

beforeEach(() => {
  init.mockClear();
  capture.mockClear();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("without a key", () => {
  it("does not initialise PostHog", async () => {
    vi.stubEnv("VITE_POSTHOG_KEY", "");

    const started = await initAnalytics();

    expect(started).toBe(false);
    expect(init).not.toHaveBeenCalled();
  });

  it("does not queue events before init", async () => {
    vi.stubEnv("VITE_POSTHOG_KEY", "");
    await initAnalytics();

    track("chat used");

    expect(capture).not.toHaveBeenCalled();
  });
});

describe("with a key", () => {
  it("initialises PostHog with it", async () => {
    vi.stubEnv("VITE_POSTHOG_KEY", "phc_test");
    vi.stubEnv("VITE_POSTHOG_HOST", "https://eu.i.posthog.com");

    const started = await initAnalytics();

    expect(started).toBe(true);
    expect(init).toHaveBeenCalledWith("phc_test", { api_host: "https://eu.i.posthog.com" });
  });

  it("falls back to the US host when none is configured", async () => {
    vi.stubEnv("VITE_POSTHOG_KEY", "phc_test");
    vi.stubEnv("VITE_POSTHOG_HOST", "");

    await initAnalytics();

    expect(init).toHaveBeenCalledWith("phc_test", { api_host: "https://us.i.posthog.com" });
  });

  it("captures events by name once initialised", async () => {
    vi.stubEnv("VITE_POSTHOG_KEY", "phc_test");
    await initAnalytics();

    track("project finder used", { device: "wasm" });

    expect(capture).toHaveBeenCalledWith("project finder used", { device: "wasm" });
  });
});
