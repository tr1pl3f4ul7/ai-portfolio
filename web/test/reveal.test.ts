/**
 * Tests for the reveal fallback.
 *
 * The property that matters most is negative: `[data-reveal]` elements must
 * never end up hidden with nothing to un-hide them. The fallback CSS is armed
 * by the `js-reveals` class, so these assert the class appears only when an
 * observer is actually going to run.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { mountReveals, prefersReducedMotion, supportsScrollDrivenAnimation } from "../src/reveal";

function stubSupports(scrollDriven: boolean): void {
  vi.stubGlobal("CSS", { supports: (rule: string) => scrollDriven && rule.includes("animation-timeline") });
}

function stubReducedMotion(reduced: boolean): void {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduced && query.includes("reduce"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

let observed: Element[];

function stubObserver(available = true): void {
  observed = [];
  if (!available) {
    vi.stubGlobal("IntersectionObserver", undefined);
    return;
  }
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      observe(target: Element): void {
        observed.push(target);
      }
      unobserve(): void {}
      disconnect(): void {}
    },
  );
}

beforeEach(() => {
  document.documentElement.className = "";
  document.body.innerHTML = `
    <section data-reveal id="a"></section>
    <section data-reveal id="b"></section>`;
  stubSupports(false);
  stubReducedMotion(false);
  stubObserver();
});

describe("capability detection", () => {
  it("detects scroll-driven animation support", () => {
    stubSupports(true);
    expect(supportsScrollDrivenAnimation()).toBe(true);
  });

  it("reports no support when CSS.supports says no", () => {
    stubSupports(false);
    expect(supportsScrollDrivenAnimation()).toBe(false);
  });

  it("detects a reduced-motion preference", () => {
    stubReducedMotion(true);
    expect(prefersReducedMotion()).toBe(true);
  });
});

describe("the fallback only arms when it will actually run", () => {
  it("observes every target and arms the CSS when it is needed", () => {
    mountReveals();

    expect(document.documentElement.classList.contains("js-reveals")).toBe(true);
    expect(observed).toHaveLength(2);
  });

  it("stays out of the way when the CSS is driving the motion", () => {
    stubSupports(true);

    mountReveals();

    // Arming here would hide sections that motion.css is already animating.
    expect(document.documentElement.classList.contains("js-reveals")).toBe(false);
    expect(observed).toHaveLength(0);
  });

  it("does nothing when reduced motion is preferred", () => {
    stubReducedMotion(true);

    mountReveals();

    expect(document.documentElement.classList.contains("js-reveals")).toBe(false);
    expect(observed).toHaveLength(0);
  });

  it("does not arm the CSS when IntersectionObserver is missing", () => {
    // The failure this prevents: content hidden by CSS with no observer to
    // reveal it — a blank page on an old browser.
    stubObserver(false);

    mountReveals();

    expect(document.documentElement.classList.contains("js-reveals")).toBe(false);
  });

  it("does not arm the CSS when there is nothing to reveal", () => {
    document.body.innerHTML = "<section></section>";

    mountReveals();

    expect(document.documentElement.classList.contains("js-reveals")).toBe(false);
  });
});
