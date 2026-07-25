/**
 * Tests for the on-device project finder.
 *
 * Real inference needs a model download, so the engine is injected here —
 * these tests cover the ranking logic and the state machine around it: the
 * model loads once, the query gets embedded, and the closest real project
 * wins. The property that matters most is that the result is always one of
 * the actual `.work-item` entries — see src/project-finder.ts for why that
 * matters (it's what replaces the earlier summariser, which invented facts).
 *
 * Actual embedding quality is verified by hand in Chrome — see
 * docs/design-system.md.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  mountProjectFinder,
  rank,
  readProjects,
  type EngineLoader,
  type FinderEngine,
  type Project,
} from "../src/project-finder";

let root: HTMLElement;

const PAGE = `
  <ol class="work">
    <li class="work-item">
      <p class="work-meta">gruntify · 2021</p>
      <h3 class="work-name">Gruntify</h3>
      <p class="work-note">GIS platform for field workers. Several clients were Australian local governments.</p>
    </li>
    <li class="work-item">
      <p class="work-meta">solvedout · 2017</p>
      <h3 class="work-name">Hellboy VR</h3>
      <p class="work-note">Dual 8K stereoscopic video on phone-driven headsets, for Lions Gate.</p>
    </li>
  </ol>`;

beforeEach(() => {
  document.body.innerHTML = `<div id="finder" class="finder"></div>${PAGE}`;
  root = document.querySelector<HTMLElement>("#finder")!;
});

/** A fake embedding space: each project gets a distinct one-hot-ish vector,
 *  and the fake engine returns whichever vector its text was tagged with. */
function fakeEngine(vectorFor: Record<string, number[]>): FinderEngine {
  return {
    async embed(texts) {
      return texts.map((text) => {
        const match = Object.keys(vectorFor).find((key) => text.includes(key));
        return match ? vectorFor[match]! : [0, 0];
      });
    },
  };
}

const form = (): HTMLFormElement => root.querySelector<HTMLFormElement>(".finder-form")!;
const input = (): HTMLInputElement => root.querySelector<HTMLInputElement>(".finder-input")!;
const status = (): HTMLElement => root.querySelector<HTMLElement>(".finder-status")!;
const output = (): HTMLElement => root.querySelector<HTMLElement>(".finder-output")!;
const cancelButton = (): HTMLButtonElement => root.querySelector<HTMLButtonElement>(".finder-cancel")!;

function ask(query: string): void {
  input().value = query;
  form().dispatchEvent(new Event("submit", { cancelable: true }));
}

/** Let the widget's async submit handler settle. */
const settle = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

describe("reading projects off the page", () => {
  it("pulls the name and note straight from the DOM, not a separate copy", () => {
    const projects = readProjects(document);

    expect(projects).toHaveLength(2);
    expect(projects[0]!.text).toBe(
      "Gruntify. GIS platform for field workers. Several clients were Australian local governments.",
    );
    expect(projects[0]!.element).toBe(document.querySelectorAll(".work-item")[0]);
  });
});

describe("ranking", () => {
  it("puts the closer vector first", () => {
    const projects: Project[] = [
      { element: document.createElement("li"), text: "a" },
      { element: document.createElement("li"), text: "b" },
    ];
    const vectors = [
      [1, 0],
      [0, 1],
    ];

    const ranked = rank([0.9, 0.1], projects, vectors);

    expect(ranked[0]).toBe(projects[0]);
    expect(ranked[1]).toBe(projects[1]);
  });
});

describe("before the visitor asks anything", () => {
  it("downloads nothing on mount", async () => {
    const loadEngine = vi.fn();
    mountProjectFinder(root, { loadEngine });
    await settle();

    expect(loadEngine).not.toHaveBeenCalled();
  });

  it("does not submit on an empty query", async () => {
    const loadEngine = vi.fn();
    mountProjectFinder(root, { loadEngine });

    ask("");
    await settle();

    expect(loadEngine).not.toHaveBeenCalled();
  });
});

describe("matching a query", () => {
  it("always resolves to one of the real work items, never invented text", async () => {
    const loadEngine: EngineLoader = async () =>
      fakeEngine({ Gruntify: [1, 0], Hellboy: [0, 1] });
    mountProjectFinder(root, { loadEngine });

    ask("local government work");
    await settle();

    expect(output().textContent).toContain("Gruntify");
    // The only names it could ever say are the real ones on the page.
    expect(output().textContent).not.toMatch(/invent|hallucinat/i);
  });

  it("names only the single closest match, not runners-up", async () => {
    const loadEngine: EngineLoader = async () =>
      fakeEngine({ Gruntify: [1, 0.9], Hellboy: [0, 1] });
    mountProjectFinder(root, { loadEngine });

    ask("anything");
    await settle();

    expect(output().textContent).toBe("Closest match: Gruntify.");
  });

  it("reports the match as on-device", async () => {
    mountProjectFinder(root, {
      loadEngine: async () => fakeEngine({ Gruntify: [1, 0], Hellboy: [0, 1] }),
    });

    ask("government");
    await settle();

    expect(status().textContent).toMatch(/on your device/);
  });

  it("reports the measured match time", async () => {
    const onMatched = vi.fn();
    mountProjectFinder(root, {
      loadEngine: async () => fakeEngine({ Gruntify: [1, 0], Hellboy: [0, 1] }),
      onMatched,
    });

    ask("government");
    await settle();

    expect(onMatched).toHaveBeenCalledOnce();
    expect(typeof onMatched.mock.calls[0]![0]).toBe("number");
  });

  it("loads the model and embeds projects once, however many queries follow", async () => {
    const loadEngine = vi.fn(async () => fakeEngine({ Gruntify: [1, 0], Hellboy: [0, 1] }));
    mountProjectFinder(root, { loadEngine });

    ask("first question");
    await settle();
    ask("second question");
    await settle();

    expect(loadEngine).toHaveBeenCalledOnce();
  });

  it("highlights the matched card without moving the page", async () => {
    mountProjectFinder(root, {
      loadEngine: async () => fakeEngine({ Gruntify: [1, 0], Hellboy: [0, 1] }),
    });
    const gruntifyCard = document.querySelectorAll(".work-item")[0]!;

    ask("government");
    await settle();

    // A visitor mid-read in this section shouldn't get yanked elsewhere
    // without asking — the match is shown, not forced into view.
    expect(gruntifyCard.classList.contains("is-matched")).toBe(true);
  });

  it("clears the previous highlight before applying a new one", async () => {
    mountProjectFinder(root, {
      loadEngine: async () => fakeEngine({ Gruntify: [1, 0], Hellboy: [0, 1] }),
    });
    const [gruntifyCard, hellboyCard] = document.querySelectorAll(".work-item");

    ask("government");
    await settle();
    ask("Hellboy stereoscopic video headsets");
    await settle();

    expect(gruntifyCard!.classList.contains("is-matched")).toBe(false);
    expect(hellboyCard!.classList.contains("is-matched")).toBe(true);
  });
});

describe("cancelling a download", () => {
  it("hides the cancel button until a download actually starts", () => {
    mountProjectFinder(root, { loadEngine: async () => fakeEngine({}) });

    expect(cancelButton().hidden).toBe(true);
  });

  it("shows the cancel button while the model is loading", async () => {
    let resolveLoad: (() => void) | undefined;
    const loadEngine: EngineLoader = () =>
      new Promise((resolve) => {
        resolveLoad = () => resolve(fakeEngine({}));
      });
    mountProjectFinder(root, { loadEngine });

    ask("anything");
    await settle();

    expect(cancelButton().hidden).toBe(false);
    resolveLoad?.();
  });

  it("actually aborts the in-flight load, not just the waiting", async () => {
    let sawAbort = false;
    const loadEngine: EngineLoader = (_onProgress, signal) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => {
          sawAbort = true;
          const error = new Error("aborted");
          error.name = "AbortError";
          reject(error);
        });
      });
    mountProjectFinder(root, { loadEngine });

    ask("anything");
    await settle();
    cancelButton().click();
    await settle();

    expect(sawAbort).toBe(true);
  });

  it("reports a cancellation distinctly from a real failure", async () => {
    const loadEngine: EngineLoader = (_onProgress, signal) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => {
          const error = new Error("aborted");
          error.name = "AbortError";
          reject(error);
        });
      });
    mountProjectFinder(root, { loadEngine });

    ask("anything");
    await settle();
    cancelButton().click();
    await settle();

    expect(status().textContent).toMatch(/cancelled/i);
    expect(status().textContent).not.toMatch(/couldn't run/i);
  });

  it("hides its own button again once loading stops, cancelled or not", async () => {
    const loadEngine: EngineLoader = (_onProgress, signal) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => {
          const error = new Error("aborted");
          error.name = "AbortError";
          reject(error);
        });
      });
    mountProjectFinder(root, { loadEngine });

    ask("anything");
    await settle();
    cancelButton().click();
    await settle();

    expect(cancelButton().hidden).toBe(true);
  });

  it("leaves the form usable again so the visitor can just try again", async () => {
    const loadEngine: EngineLoader = (_onProgress, signal) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => {
          const error = new Error("aborted");
          error.name = "AbortError";
          reject(error);
        });
      });
    mountProjectFinder(root, { loadEngine });

    ask("anything");
    await settle();
    cancelButton().click();
    await settle();

    expect(input().disabled).toBe(false);
    expect(root.querySelector<HTMLButtonElement>(".finder-run")!.disabled).toBe(false);
  });
});

describe("when there is nothing to match against", () => {
  it("says so instead of matching nothing silently", async () => {
    document.body.innerHTML = `<div id="finder" class="finder"></div>`;
    root = document.querySelector<HTMLElement>("#finder")!;

    mountProjectFinder(root, { loadEngine: async () => fakeEngine({}) });

    ask("anything");
    await settle();

    expect(output().textContent).toMatch(/no projects/i);
  });
});

describe("when it goes wrong", () => {
  it("surfaces the failure instead of hanging", async () => {
    mountProjectFinder(root, {
      loadEngine: async () => {
        throw new Error("out of memory");
      },
    });

    ask("anything");
    await settle();

    expect(status().textContent).toMatch(/out of memory/);
  });

  it("re-enables the form so it can be retried", async () => {
    mountProjectFinder(root, {
      loadEngine: async () => {
        throw new Error("device lost");
      },
    });

    ask("anything");
    await settle();

    expect(input().disabled).toBe(false);
    expect(root.querySelector<HTMLButtonElement>(".finder-run")!.disabled).toBe(false);
  });
});
