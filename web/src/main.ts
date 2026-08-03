/**
 * Entry point. Mounts the widgets and the scroll reveals.
 *
 * Nothing here starts a model download or blocks first paint — the page must be
 * fast before any AI runs (web/CLAUDE.md). The on-device project finder is
 * Step 3.3, behind an explicit click.
 */

import { initAnalytics, track } from "./analytics";
import { getAskContent, getBrowserContent, getContactContent, getProfile, getProjects } from "./api";
import { mountChat } from "./chat";
import { mountContact } from "./contact";
import { API_BASE_URL } from "./config";
import { mountMotion } from "./motion";
import { initSentry, reportError } from "./observability";
import { mountProjectFinder } from "./project-finder";
import { renderContent, type PageContent } from "./render-content";

// Init as early as possible so both catch anything that happens below —
// no-ops without a key/DSN, which is the case on a dev machine and in CI.
// Neither blocks anything: both are dynamically imported (see the two
// modules), so this fires the fetch for their code without waiting on it.
const sentryReady = initSentry();
void initAnalytics();

// A hidden, deliberate trigger for verifying Sentry actually captures
// something real, the same shape as the backend's hidden /debug/error route.
// Visit ?debug-error to use it; there is no link to it anywhere on the page.
// Waits on initSentry() itself rather than guessing a delay, since it now
// has its own dynamic import to finish first.
if (new URLSearchParams(location.search).has("debug-error")) {
  void sentryReady.then(() => {
    throw new Error("Deliberate test error for Sentry verification (web/CLAUDE.md).");
  });
}

/** Write a measured time into the trace rows for the layers that just ran. */
function record(layers: string[], elapsedMs: number): void {
  const seconds = `${(elapsedMs / 1000).toFixed(2)}s`;
  for (const layer of layers) {
    const cost = document.querySelector<HTMLElement>(`[data-layer="${layer}"] [data-cost]`);
    if (!cost) continue;
    cost.textContent = seconds;
    cost.classList.add("is-measured");
  }
}

/**
 * Show a real measurement on the layers that just did the work.
 *
 * The chat exercises retrieval on the VM and generation at the Claude API, so
 * those two rows — and only those two — get the number. The edge row stays as
 * it is until something actually runs there.
 */
function recordRoundTrip(elapsedMs: number): void {
  record(["server", "cloud"], elapsedMs);
  track("chat used");
}

/** The project finder runs entirely in the browser, so only that row moves. */
function recordOnDevice(elapsedMs: number): void {
  record(["browser"], elapsedMs);
  track("project finder used");
}

// The link ships with a same-origin placeholder href in index.html so it still
// works if this never runs; here it's pointed at the real backend origin, the
// same way every fetch() in api.ts is.
const resumeLink = document.querySelector<HTMLAnchorElement>("#resume-link");
if (resumeLink) {
  resumeLink.href = `${API_BASE_URL}/resume`;
  resumeLink.addEventListener("click", () => track("resume downloaded"));
}

mountMotion();

/**
 * Show something honest if the content fetch fails, rather than a page with
 * a blank hero and no explanation (web/CLAUDE.md: "degrade honestly").
 * Reported to Sentry too — a caught error is otherwise invisible to it.
 */
function showContentLoadFailure(error: unknown): void {
  console.error("Failed to load page content:", error);
  void reportError(error);

  const hero = document.querySelector<HTMLElement>(".hero-intro");
  if (!hero) return;
  hero.replaceChildren();
  const message = document.createElement("p");
  message.className = "lede";
  message.textContent = "Content failed to load. Try refreshing.";
  hero.append(message);
}

/**
 * Every section's text — hero, section copy, the project cards — comes from
 * the backend now (decision 57), not hardcoded HTML. Fetched once, up front,
 * before anything mounts: a widget that mounted against empty content would
 * be a worse failure mode than the whole page waiting the extra moment this
 * takes, which given the payload size here is close to nothing.
 */
void (async () => {
  let content: PageContent;
  try {
    const [profile, browser, ask, contact, projects] = await Promise.all([
      getProfile(),
      getBrowserContent(),
      getAskContent(),
      getContactContent(),
      getProjects(),
    ]);
    content = { profile, browser, ask, contact, projects };
  } catch (error) {
    showContentLoadFailure(error);
    return;
  }

  renderContent(content);

  // The project cards don't exist yet when mountMotion() runs above — they're
  // created here, after the fetch resolves. Without this, they'd match
  // motion.css's `.js-motion .work-item { opacity: 0 }` but never get
  // observed, so they'd never receive `.is-revealed` and would stay invisible
  // forever. mountMotion() is idempotent, so scoping a second call to this
  // subtree wires just the new cards in without touching anything already
  // settled elsewhere on the page.
  const workList = document.querySelector<HTMLElement>("#work-list");
  if (workList) mountMotion(workList);

  const finder = document.querySelector<HTMLElement>("#finder");
  if (finder) mountProjectFinder(finder, { onMatched: recordOnDevice });

  const chat = document.querySelector<HTMLElement>("#chat");
  if (chat) mountChat(chat, { onAnswered: recordRoundTrip, suggestions: content.ask.suggestions });

  const contactEl = document.querySelector<HTMLElement>("#contact");
  if (contactEl) mountContact(contactEl, { onSubmitted: () => track("form submitted") });
})();
