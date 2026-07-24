/**
 * Scroll-triggered reveals.
 *
 * IntersectionObserver rather than a scroll handler: the browser does the work
 * off the main thread and there is no listener firing on every frame.
 *
 * `prefers-reduced-motion` is honoured by revealing everything immediately and
 * never observing anything — non-negotiable, per web/CLAUDE.md.
 */

const REVEALED = "is-revealed";

export function mountReveals(root: ParentNode = document): void {
  const targets = Array.from(root.querySelectorAll<HTMLElement>("[data-reveal]"));
  if (targets.length === 0) return;

  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  if (reduced || typeof IntersectionObserver === "undefined") {
    for (const target of targets) target.classList.add(REVEALED);
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add(REVEALED);
        // Reveal once. Re-animating on scroll-back is noise, not delight.
        observer.unobserve(entry.target);
      }
    },
    // Fire slightly before the element reaches the viewport edge so the motion
    // finishes as it arrives rather than starting late.
    { rootMargin: "0px 0px -12% 0px", threshold: 0.05 },
  );

  for (const target of targets) observer.observe(target);
}
