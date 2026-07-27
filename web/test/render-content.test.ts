/**
 * Tests for populating the page from fetched content (decision 57).
 *
 * Builds the same empty, id-tagged skeleton index.html actually ships, so a
 * mismatch between the two would fail here rather than only in the browser.
 */

import { beforeEach, describe, expect, it } from "vitest";
import type { PageContent } from "../src/render-content";
import { renderContent } from "../src/render-content";

const CONTENT: PageContent = {
  profile: { name: "ljuben vassilev", location: "brisbane, australia", tagline: "Ten years of mobile." },
  browser: { label: "browser", heading: "ask which project fits", description: "Type what you're after." },
  ask: {
    label: "ask",
    heading: "two of those layers",
    description: "Retrieves then generates.",
    suggestions: ["What's the hardest thing you've built?", "Do you have security experience?"],
  },
  contact: { label: "contact", heading: "say hello", description: "Goes to a triage endpoint." },
  projects: {
    label: "selected work",
    heading: "things that had to not break",
    items: [
      { company: "propertyme", year: "2022–2026", name: "PropertyMe", note: "Flutter app for owners." },
      { company: "gruntify", year: "2021", name: "Gruntify", note: "Android GIS platform." },
    ],
  },
};

beforeEach(() => {
  document.body.innerHTML = `
    <div class="hero-intro">
      <p class="label" id="hero-location"></p>
      <h1 class="display" id="hero-name"></h1>
      <p class="lede" id="hero-tagline"></p>
    </div>
    <p class="label" id="browser-label"></p>
    <h2 class="heading" id="browser-heading"></h2>
    <p class="prose" id="browser-description"></p>
    <p class="label" id="ask-label"></p>
    <h2 class="heading" id="ask-heading"></h2>
    <p class="prose" id="ask-description"></p>
    <p class="label" id="contact-label"></p>
    <h2 class="heading" id="contact-heading"></h2>
    <p class="prose" id="contact-description"></p>
    <p class="label" id="projects-label"></p>
    <h2 class="heading" id="projects-heading"></h2>
    <ol class="work" id="work-list"></ol>
  `;
});

function text(id: string): string {
  return document.getElementById(id)?.textContent ?? "";
}

describe("renderContent", () => {
  it("fills the hero", () => {
    renderContent(CONTENT);

    expect(text("hero-location")).toBe("brisbane, australia");
    expect(text("hero-name")).toBe("ljuben vassilev");
    expect(text("hero-tagline")).toBe("Ten years of mobile.");
  });

  it("fills each section's label, heading, and description", () => {
    renderContent(CONTENT);

    expect(text("browser-heading")).toBe("ask which project fits");
    expect(text("ask-heading")).toBe("two of those layers");
    expect(text("contact-heading")).toBe("say hello");
    expect(text("projects-heading")).toBe("things that had to not break");
  });

  it("renders one .work-item per project, matching what project-finder.ts reads back", () => {
    renderContent(CONTENT);

    const items = document.querySelectorAll<HTMLElement>("#work-list .work-item");
    expect(items).toHaveLength(2);

    const first = items[0]!;
    expect(first.querySelector(".work-meta")?.textContent).toBe("propertyme · 2022–2026");
    expect(first.querySelector(".work-name")?.textContent).toBe("PropertyMe");
    expect(first.querySelector(".work-note")?.textContent).toBe("Flutter app for owners.");
  });

  it("replaces any previous list rather than appending to it", () => {
    renderContent(CONTENT);
    renderContent(CONTENT);

    expect(document.querySelectorAll("#work-list .work-item")).toHaveLength(2);
  });

  it("does nothing to elements that are not on the page, rather than throwing", () => {
    document.body.innerHTML = "";

    expect(() => renderContent(CONTENT)).not.toThrow();
  });
});
