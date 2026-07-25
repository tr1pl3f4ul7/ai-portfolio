/**
 * Entry point. Mounts the widgets and the scroll reveals.
 *
 * Nothing here starts a model download or blocks first paint — the page must be
 * fast before any AI runs (web/CLAUDE.md). The on-device project finder is
 * Step 3.3, behind an explicit click.
 */

import { initAnalytics, track } from "./analytics";
import { mountChat } from "./chat";
import { mountContact } from "./contact";
import { mountMotion } from "./motion";
import { initSentry } from "./observability";
import { mountProjectFinder } from "./project-finder";

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

const finder = document.querySelector<HTMLElement>("#finder");
if (finder) mountProjectFinder(finder, { onMatched: recordOnDevice });

const chat = document.querySelector<HTMLElement>("#chat");
if (chat) mountChat(chat, { onAnswered: recordRoundTrip });

const contact = document.querySelector<HTMLElement>("#contact");
if (contact) mountContact(contact, { onSubmitted: () => track("form submitted") });

mountMotion();
