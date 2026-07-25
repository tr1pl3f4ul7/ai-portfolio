/**
 * The browser inference layer — semantic search over my real projects,
 * running entirely on the visitor's own hardware.
 *
 * This replaced an earlier on-device *summariser* (docs/decisions.md, decision
 * 44). That version asked a sub-1B model to freely generate prose about my
 * career, and it did what small generative models do under those conditions:
 * invented things — "ten years in AI development", "languages including
 * Unity3D". No amount of prompting reliably stops a model this size from
 * filling gaps with plausible-sounding fiction, on a page whose whole
 * argument is that the numbers and claims here are real.
 *
 * Retrieval removes that failure mode instead of mitigating it. This widget
 * embeds the real `<li class="work-item">` entries already in index.html,
 * embeds whatever the visitor typed, and reports which project sits closest
 * by cosine similarity. The output is always one of those real entries — the
 * model has no way to say anything untrue, because it isn't saying anything;
 * it's pointing.
 *
 * That also sidesteps the two problems the generative version hit:
 *   - **Size.** An encoder-only embedding model needs no KV cache and is a
 *     fraction of a decoder's size for comparable quality. ~54 MB (q4) here,
 *     against the ~500 MB the generative version needed.
 *   - **Speed.** One forward pass over a short sentence, not an autoregressive
 *     loop generating token by token. The generative version measured 283s
 *     for one summary on WASM; embedding a short query measures in
 *     milliseconds.
 *
 * Cheap enough per call that the WebGPU/WASM device split the generative
 * version needed isn't worth its complexity here — WASM alone is fast enough
 * that chasing GPU acceleration would be more code with no visible benefit.
 * transformers.js is still loaded with a dynamic `import()` so it stays out
 * of the initial bundle and out of the jsdom tests, which inject a fake
 * engine instead.
 */

const MODEL_ID = "onnx-community/all-MiniLM-L6-v2-ONNX";
const DTYPE = "q4";

/** How long a matched project stays highlighted before the outline fades. */
const HIGHLIGHT_MS = 2200;

export type ProgressCallback = (fraction: number, label: string) => void;

/** A project pulled from the page, embedded once and matched repeatedly. */
export interface Project {
  element: HTMLElement;
  text: string;
}

/** The slice of transformers.js this widget actually uses, so tests can supply a fake. */
export interface FinderEngine {
  embed(texts: string[]): Promise<number[][]>;
}

export type EngineLoader = (onProgress: ProgressCallback, signal: AbortSignal) => Promise<FinderEngine>;

/** True for the error an aborted fetch rejects with, in any engine. */
function isAbortError(error: unknown): boolean {
  return typeof error === "object" && error !== null && (error as { name?: unknown }).name === "AbortError";
}

/** Read the real project cards straight from the page — no separate copy to drift out of sync. */
export function readProjects(root: ParentNode = document): Project[] {
  return Array.from(root.querySelectorAll<HTMLElement>(".work-item")).map((element) => {
    const name = element.querySelector(".work-name")?.textContent?.trim() ?? "";
    const note = element.querySelector(".work-note")?.textContent?.trim() ?? "";
    return { element, text: `${name}. ${note}` };
  });
}

/** Plain cosine similarity. Hand-rolled rather than imported so nothing from
 *  transformers.js reaches the eagerly-loaded bundle — the whole package is
 *  behind the dynamic import in `loadEngine` below. */
function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i]! * b[i]!;
    normA += a[i]! * a[i]!;
    normB += b[i]! * b[i]!;
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

/** Rank projects against a query embedding, closest first. */
export function rank(queryVector: number[], projects: Project[], vectors: number[][]): Project[] {
  return projects
    .map((project, index) => ({ project, score: cosineSimilarity(queryVector, vectors[index]!) }))
    .sort((a, b) => b.score - a.score)
    .map((entry) => entry.project);
}

/**
 * The real loader. Pulls transformers.js on demand and adapts its pipeline to
 * `FinderEngine`.
 *
 * transformers.js exposes no `signal` option on `pipeline()` itself, but every
 * download goes through the overridable `env.fetch` hook (confirmed by reading
 * the installed package's source, not assumed). Wrapping it with our own
 * AbortController-aware fetch is what makes a real cancel button possible —
 * the in-flight request actually stops, rather than the widget merely
 * pretending not to be waiting for it any more.
 */
export const loadEngine: EngineLoader = async (onProgress, signal) => {
  const { pipeline, env } = await import("@huggingface/transformers");

  const previousFetch = env.fetch;
  env.fetch = (input, init) => previousFetch(input, { ...init, signal });

  try {
    const extractor = await pipeline("feature-extraction", MODEL_ID, {
      device: "wasm",
      dtype: DTYPE,
      progress_callback: (info: { status: string; progress?: number; file?: string }) => {
        if (info.status === "progress_total" && typeof info.progress === "number") {
          onProgress(info.progress / 100, `fetching ${info.file ?? "the model"}…`);
        } else if (info.status === "ready") {
          // The download can reach 100% well before the ONNX session finishes
          // building from those bytes — an unlabelled gap reads as "stuck".
          onProgress(1, "model downloaded, starting it up…");
        }
      },
    });

    return {
      async embed(texts) {
        const output = await extractor(texts, { pooling: "mean", normalize: true });
        return output.tolist() as number[][];
      },
    };
  } finally {
    // Restore rather than leave every future fetch in the app tied to a
    // signal from one finished (or abandoned) load attempt.
    env.fetch = previousFetch;
  }
};

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

export interface FinderOptions {
  /** Swapped in tests. Defaults to the real transformers.js loader. */
  loadEngine?: EngineLoader;
  /** Swapped in tests. Defaults to reading `.work-item` elements from the page. */
  readProjects?: () => Project[];
  /**
   * Called after each match with the time the match itself took — embedding
   * the query and ranking it, not the one-time model download. Lets the
   * inference trace show a real number for the browser layer, the same way
   * the chat does for the server and cloud rows.
   */
  onMatched?: (elapsedMs: number) => void;
}

export function mountProjectFinder(root: HTMLElement, options: FinderOptions = {}): void {
  const load = options.loadEngine ?? loadEngine;
  const getProjects = options.readProjects ?? (() => readProjects());

  root.replaceChildren();

  const form = el("form", "finder-form");
  form.setAttribute("novalidate", "");

  const label = el("label", "sr-only", "Ask which project fits");
  label.htmlFor = "finder-input";

  const input = el("input", "finder-input");
  input.id = "finder-input";
  input.type = "text";
  input.placeholder = 'e.g. "anything with government clients?"';
  input.autocomplete = "off";

  const button = el("button", "finder-run", "find a project");
  button.type = "submit";

  form.append(label, input, button);

  const status = el("p", "finder-status");
  status.setAttribute("aria-live", "polite");

  const track = el("div", "finder-track");
  const bar = el("div", "finder-bar");
  track.append(bar);
  track.hidden = true;

  const cancel = el("button", "finder-cancel", "cancel download");
  cancel.type = "button";
  cancel.hidden = true;

  const output = el("p", "finder-output");
  output.setAttribute("aria-live", "polite");

  root.append(form, status, track, cancel, output);

  const setProgress = (fraction: number): void => {
    track.hidden = false;
    cancel.hidden = false;
    bar.style.setProperty("--progress", String(Math.max(0, Math.min(1, fraction))));
  };

  const hideProgress = (): void => {
    track.hidden = true;
    cancel.hidden = true;
  };

  let engine: FinderEngine | null = null;
  let projects: Project[] = [];
  let vectors: number[][] = [];
  let running = false;
  let controller: AbortController | null = null;
  let highlighted: HTMLElement | null = null;
  let highlightTimer: ReturnType<typeof setTimeout> | undefined;

  cancel.addEventListener("click", () => {
    controller?.abort();
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (running) return;

    const query = input.value.trim();
    if (!query) return;

    running = true;
    button.disabled = true;
    input.disabled = true;
    output.textContent = "";

    void (async () => {
      try {
        if (!engine) {
          projects = getProjects();
          status.textContent = "loading the model…";
          setProgress(0);

          controller = new AbortController();
          engine = await load((fraction, label) => {
            setProgress(fraction);
            if (label) status.textContent = label;
          }, controller.signal);
          controller = null;

          hideProgress();
          status.textContent = "reading my projects…";
          vectors = projects.length > 0 ? await engine.embed(projects.map((p) => p.text)) : [];
        }

        status.textContent = "matching your question…";
        const started = performance.now();
        const [queryVector] = await engine.embed([query]);
        const [best] = rank(queryVector!, projects, vectors);
        const elapsedMs = performance.now() - started;

        if (!best) {
          status.textContent = "";
          output.textContent = "No projects on the page to match against.";
          return;
        }

        status.textContent = `matched entirely on your device · ${(elapsedMs / 1000).toFixed(2)}s`;
        options.onMatched?.(elapsedMs);
        const name = best.element.querySelector(".work-name")?.textContent ?? "";
        output.textContent = `Closest match: ${name}.`;

        // Points at the match without moving the page — a visitor mid-read in
        // this section shouldn't get yanked somewhere else without asking.
        clearTimeout(highlightTimer);
        highlighted?.classList.remove("is-matched");
        highlighted = best.element;
        highlighted.classList.add("is-matched");
        highlightTimer = setTimeout(() => highlighted?.classList.remove("is-matched"), HIGHLIGHT_MS);
      } catch (error) {
        status.textContent = isAbortError(error)
          ? "Cancelled — nothing was kept."
          : error instanceof Error && error.message
            ? `Couldn't run the model: ${error.message}`
            : "Couldn't run the model on this device.";
        hideProgress();
      } finally {
        controller = null;
        running = false;
        button.disabled = false;
        input.disabled = false;
      }
    })();
  });
}
