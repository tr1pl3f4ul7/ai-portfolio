/**
 * Scroll and load motion.
 *
 * Class-toggle driven, not CSS-scroll-timeline driven, and that is a deliberate
 * reversal. The first attempt put `view()` timelines on whole `<section>`
 * elements; a section taller than the viewport has a degenerate `entry` range,
 * so those animations completed before the section was ever on screen and
 * nothing appeared to move. Toggling a class from an IntersectionObserver and
 * letting CSS transition the result is what the reference sites do, it works at
 * any element height, and — unlike a compositor-driven timeline — it can be
 * asserted on in tests.
 *
 * Continuous parallax stays in CSS (motion.css), because that genuinely wants a
 * scroll timeline and runs off the main thread.
 *
 * Text is split into words so headings can rise from behind a mask. The split
 * is aria-hidden with the original text preserved on the parent, so a screen
 * reader gets one clean string rather than a stream of fragments.
 */

const ARMED = "js-motion";
const REVEALED = "is-revealed";

/** Elements that reveal on scroll. Kept here rather than as markup attributes
 *  so the HTML stays readable and the set is easy to reason about. */
const REVEAL_SELECTOR = [
  ".hero .trace",
  ".trace-row",
  ".section-head > *",
  ".prose",
  ".finder",
  ".chat",
  ".work-item",
  ".contact-form .field",
  ".contact-form .contact-send",
  ".footer > *",
].join(",");

/** Headings that get the per-word masked reveal. */
const SPLIT_SELECTOR = ".display, .heading";

export function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

/**
 * Wrap each word in a mask so it can slide up from nothing.
 *
 * Produces `<span class="mask"><span class="word" style="--i:N">…</span></span>`
 * per word. Idempotent: an already-split element is left alone.
 */
export function splitWords(element: HTMLElement, startIndex = 0): number {
  if (element.dataset.split === "done") return startIndex;

  const text = element.textContent?.trim() ?? "";
  if (!text) return startIndex;

  // Preserve the readable string before shredding it into spans.
  element.setAttribute("aria-label", text);

  const fragment = document.createDocumentFragment();
  let index = startIndex;

  for (const word of text.split(/\s+/)) {
    const mask = document.createElement("span");
    mask.className = "mask";
    mask.setAttribute("aria-hidden", "true");

    const inner = document.createElement("span");
    inner.className = "word";
    inner.style.setProperty("--i", String(index));
    inner.textContent = word;

    mask.append(inner);
    fragment.append(mask, document.createTextNode(" "));
    index += 1;
  }

  element.replaceChildren(fragment);
  element.dataset.split = "done";
  return index;
}

/**
 * Mark each target and give siblings a cascade index.
 *
 * The attribute is what the CSS hides against — set here rather than in the
 * markup so the hidden state can only ever exist alongside the observer that
 * undoes it.
 */
function prepare(elements: HTMLElement[]): void {
  const seen = new Map<Element, number>();
  for (const element of elements) {
    element.setAttribute("data-reveal-target", "");
    const parent = element.parentElement ?? document.body;
    const index = seen.get(parent) ?? 0;
    element.style.setProperty("--i", String(index));
    seen.set(parent, index + 1);
  }
}

function reveal(element: HTMLElement): void {
  element.classList.add(REVEALED);
}

export function mountMotion(root: ParentNode = document): void {
  const targets = Array.from(root.querySelectorAll<HTMLElement>(REVEAL_SELECTOR));
  const headings = Array.from(root.querySelectorAll<HTMLElement>(SPLIT_SELECTOR));

  // Split first: the word spans need to exist before anything reveals them.
  for (const heading of headings) splitWords(heading);

  if (prefersReducedMotion() || typeof IntersectionObserver === "undefined") {
    // Everything visible, nothing hidden, no observer. The page is complete.
    for (const target of targets) reveal(target);
    for (const heading of headings) reveal(heading);
    return;
  }

  // Only now, with an observer guaranteed to run, is it safe for the CSS to
  // hide anything. Without this gate a browser lacking IntersectionObserver
  // would render a blank page.
  document.documentElement.classList.add(ARMED);

  prepare(targets);

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        reveal(entry.target as HTMLElement);
        // Once is enough. Re-animating on scroll-back is noise.
        observer.unobserve(entry.target);
      }
    },
    // Start slightly before the element reaches the edge so the travel finishes
    // as it arrives, rather than beginning once it is already in place.
    { rootMargin: "0px 0px -10% 0px", threshold: 0.01 },
  );

  for (const target of targets) observer.observe(target);

  // Headings inside a revealed container ride that container's reveal; the two
  // standalone ones (hero display, section headings) get their own observer
  // entry so their words cascade on entry rather than on load.
  for (const heading of headings) observer.observe(heading);

  // The hero is above the fold, so nothing will ever scroll it into view — it
  // needs a load sequence instead.
  //
  // This runs SYNCHRONOUSLY, not in a requestAnimationFrame. rAF is the
  // conventional way to let the browser commit the hidden state before
  // transitioning away from it, but it does not fire in a background tab or in
  // an embedder that is not compositing — and a hero that never reveals is a
  // page with an invisible headline. Observed exactly that during development.
  //
  // Reading offsetHeight forces a style flush, which gives the transition a
  // computed "from" state to start at, with no dependency on a frame arriving.
  const hero = root.querySelector<HTMLElement>(".hero");
  if (hero) {
    void document.body.offsetHeight;
    for (const element of hero.querySelectorAll<HTMLElement>(`${REVEAL_SELECTOR}, ${SPLIT_SELECTOR}`)) {
      reveal(element);
      observer.unobserve(element);
    }
    hero.classList.add(REVEALED);
  }
}
