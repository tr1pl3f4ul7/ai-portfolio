/**
 * Tests for the motion engine.
 *
 * These are possible *because* the engine toggles classes rather than driving a
 * CSS scroll timeline: a class change is observable without a compositor, so the
 * behaviour can be asserted here instead of only by eye.
 *
 * The property that matters most is negative — content must never end up hidden
 * with nothing to reveal it. The hidden state is gated behind `js-motion`, which
 * may only appear when an observer is guaranteed to run.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { mountMotion, prefersReducedMotion, splitWords } from "../src/motion";

let observed: Element[];
let trigger: (entries: { target: Element; isIntersecting: boolean }[]) => void;

function stubObserver(available = true): void {
  observed = [];
  if (!available) {
    vi.stubGlobal("IntersectionObserver", undefined);
    return;
  }
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(callback: (entries: unknown[]) => void) {
        trigger = (entries) => callback(entries);
      }
      observe(target: Element): void {
        observed.push(target);
      }
      unobserve(target: Element): void {
        observed = observed.filter((o) => o !== target);
      }
      disconnect(): void {}
    },
  );
}

function stubReducedMotion(reduced: boolean): void {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduced && query.includes("reduce"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

const PAGE = `
  <div class="hero">
    <div class="hero-intro"><h1 class="display">ljuben vassilev</h1></div>
    <section class="trace">
      <div class="trace-row" data-layer="browser"></div>
      <div class="trace-row" data-layer="edge"></div>
    </section>
  </div>
  <section class="section">
    <div class="section-head"><p class="label">work</p><h2 class="heading">things that shipped</h2></div>
    <p class="prose">Some prose.</p>
    <ol class="work">
      <li class="work-item"><h3>A</h3></li>
      <li class="work-item"><h3>B</h3></li>
      <li class="work-item"><h3>C</h3></li>
    </ol>
  </section>
  <footer class="footer"><p>one</p><p>two</p></footer>`;

beforeEach(() => {
  document.documentElement.className = "";
  document.body.innerHTML = PAGE;
  stubReducedMotion(false);
  stubObserver();
  // Deliberately NOT stubbing requestAnimationFrame — the hero load sequence
  // must not depend on a frame arriving. See the test below.
});

describe("splitting text for masked reveals", () => {
  it("wraps every word in its own mask", () => {
    const heading = document.querySelector<HTMLElement>(".display")!;

    splitWords(heading);

    expect(heading.querySelectorAll(".mask")).toHaveLength(2);
    expect(heading.querySelectorAll(".word")).toHaveLength(2);
    expect([...heading.querySelectorAll(".word")].map((w) => w.textContent)).toEqual([
      "ljuben",
      "vassilev",
    ]);
  });

  it("indexes words so CSS can stagger them", () => {
    const heading = document.querySelector<HTMLElement>(".display")!;

    splitWords(heading);

    const words = [...heading.querySelectorAll<HTMLElement>(".word")];
    expect(words[0]!.style.getPropertyValue("--i")).toBe("0");
    expect(words[1]!.style.getPropertyValue("--i")).toBe("1");
  });

  it("keeps the text readable for screen readers", () => {
    // Shredding a heading into spans would otherwise be announced word by word.
    const heading = document.querySelector<HTMLElement>(".display")!;

    splitWords(heading);

    expect(heading.getAttribute("aria-label")).toBe("ljuben vassilev");
    for (const mask of heading.querySelectorAll(".mask")) {
      expect(mask.getAttribute("aria-hidden")).toBe("true");
    }
  });

  it("is idempotent", () => {
    const heading = document.querySelector<HTMLElement>(".display")!;

    splitWords(heading);
    splitWords(heading);

    expect(heading.querySelectorAll(".word")).toHaveLength(2);
  });

  it("leaves an empty element alone", () => {
    const empty = document.createElement("h2");
    expect(() => splitWords(empty)).not.toThrow();
    expect(empty.querySelectorAll(".word")).toHaveLength(0);
  });
});

describe("arming", () => {
  it("arms the hidden state and observes every target", () => {
    mountMotion();

    expect(document.documentElement.classList.contains("js-motion")).toBe(true);
    // Targets get an attribute the CSS hides against.
    expect(document.querySelectorAll("[data-reveal-target]").length).toBeGreaterThan(5);
  });

  it("never arms when IntersectionObserver is missing", () => {
    // The failure this prevents is a blank page: CSS hiding content with
    // nothing able to reveal it.
    stubObserver(false);

    mountMotion();

    expect(document.documentElement.classList.contains("js-motion")).toBe(false);
  });

  it("never arms under reduced motion, and reveals everything instead", () => {
    stubReducedMotion(true);

    mountMotion();

    expect(document.documentElement.classList.contains("js-motion")).toBe(false);
    expect(document.querySelector(".work-item")!.classList.contains("is-revealed")).toBe(true);
    expect(document.querySelector(".prose")!.classList.contains("is-revealed")).toBe(true);
  });

  it("still splits headings under reduced motion, so layout is identical", () => {
    stubReducedMotion(true);

    mountMotion();

    expect(document.querySelectorAll(".display .word")).toHaveLength(2);
  });

  it("reports a reduced-motion preference", () => {
    stubReducedMotion(true);
    expect(prefersReducedMotion()).toBe(true);
  });
});

describe("staggering", () => {
  it("indexes siblings so a cascade is possible", () => {
    mountMotion();

    const items = [...document.querySelectorAll<HTMLElement>(".work-item")];
    expect(items.map((i) => i.style.getPropertyValue("--i"))).toEqual(["0", "1", "2"]);
  });

  it("restarts the index per parent", () => {
    mountMotion();

    const footerItems = [...document.querySelectorAll<HTMLElement>(".footer > *")];
    expect(footerItems[0]!.style.getPropertyValue("--i")).toBe("0");
  });
});

describe("revealing on scroll", () => {
  it("reveals a target when it intersects", () => {
    mountMotion();
    const item = document.querySelector<HTMLElement>(".work-item")!;
    expect(item.classList.contains("is-revealed")).toBe(false);

    trigger([{ target: item, isIntersecting: true }]);

    expect(item.classList.contains("is-revealed")).toBe(true);
  });

  it("leaves a target alone until it intersects", () => {
    mountMotion();
    const item = document.querySelector<HTMLElement>(".work-item")!;

    trigger([{ target: item, isIntersecting: false }]);

    expect(item.classList.contains("is-revealed")).toBe(false);
  });

  it("stops observing once revealed, so it cannot re-animate", () => {
    mountMotion();
    const item = document.querySelector<HTMLElement>(".work-item")!;
    const before = observed.length;

    trigger([{ target: item, isIntersecting: true }]);

    expect(observed.length).toBe(before - 1);
  });

  it("reveals section headings so their words cascade", () => {
    mountMotion();
    const heading = document.querySelector<HTMLElement>(".heading")!;

    trigger([{ target: heading, isIntersecting: true }]);

    expect(heading.classList.contains("is-revealed")).toBe(true);
  });
});

describe("the hero runs as a load sequence", () => {
  it("reveals hero content immediately rather than waiting for scroll", () => {
    // Nothing above the fold would ever intersect, so it would sit hidden.
    mountMotion();

    expect(document.querySelector(".display")!.classList.contains("is-revealed")).toBe(true);
    expect(document.querySelector(".trace")!.classList.contains("is-revealed")).toBe(true);
    for (const row of document.querySelectorAll(".trace-row")) {
      expect(row.classList.contains("is-revealed")).toBe(true);
    }
  });

  it("does not reveal below-the-fold content on load", () => {
    mountMotion();

    expect(document.querySelector(".work-item")!.classList.contains("is-revealed")).toBe(false);
    expect(document.querySelector(".prose")!.classList.contains("is-revealed")).toBe(false);
  });

  it("reveals the hero without waiting for an animation frame", () => {
    // Regression: the load sequence used requestAnimationFrame, which does not
    // fire in a background tab or a non-compositing embedder — leaving the
    // headline permanently invisible. Break rAF entirely and it must still work.
    vi.stubGlobal("requestAnimationFrame", () => {
      throw new Error("requestAnimationFrame must not be required to show the hero");
    });

    mountMotion();

    expect(document.querySelector(".display")!.classList.contains("is-revealed")).toBe(true);
    expect(document.querySelector(".hero .trace")!.classList.contains("is-revealed")).toBe(true);
  });

  it("stops observing hero elements, so scrolling back cannot re-hide them", () => {
    mountMotion();

    const display = document.querySelector(".display")!;
    expect(observed).not.toContain(display);
  });
});
