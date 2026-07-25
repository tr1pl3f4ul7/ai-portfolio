/**
 * Fallback reveals for browsers without CSS scroll-driven animations.
 *
 * The real motion lives in motion.css and is driven by `animation-timeline`,
 * which the browser runs off the main thread. This module exists only for
 * engines that don't support it: it adds `js-reveals` to <html> — which is what
 * arms the fallback CSS — and then reveals each section once on entry.
 *
 * The ordering matters for a reason that has bitten this kind of code before:
 * the fallback CSS hides `[data-reveal]` elements, so it must never apply
 * unless something is guaranteed to un-hide them. Gating it behind a class this
 * module owns means a browser where neither path runs shows a complete, static
 * page rather than a blank one.
 */

const REVEALED = "is-revealed";
const ARMED = "js-reveals";

/** True when motion.css is already handling this with scroll-linked animation. */
export function supportsScrollDrivenAnimation(): boolean {
  return typeof CSS !== "undefined" && CSS.supports?.("animation-timeline: view()") === true;
}

export function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

export function mountReveals(root: ParentNode = document): void {
  // Nothing to do: either the CSS is driving it, or the visitor asked for calm.
  if (supportsScrollDrivenAnimation() || prefersReducedMotion()) return;
  if (typeof IntersectionObserver === "undefined") return;

  const targets = Array.from(root.querySelectorAll<HTMLElement>("[data-reveal]"));
  if (targets.length === 0) return;

  // Only now, with an observer about to run, is it safe to let the CSS hide them.
  document.documentElement.classList.add(ARMED);

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add(REVEALED);
        // Reveal once. Re-animating on scroll-back is noise, not delight.
        observer.unobserve(entry.target);
      }
    },
    { rootMargin: "0px 0px -12% 0px", threshold: 0.05 },
  );

  for (const target of targets) observer.observe(target);
}
