/**
 * Entry point. Mounts the widgets and the scroll reveals.
 *
 * Nothing here starts a model download or blocks first paint — the page must be
 * fast before any AI runs (web/CLAUDE.md). The on-device project finder is
 * Step 3.3, behind an explicit click.
 */

import { mountChat } from "./chat";
import { mountContact } from "./contact";
import { mountMotion } from "./motion";
import { mountProjectFinder } from "./project-finder";

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
}

/** The project finder runs entirely in the browser, so only that row moves. */
function recordOnDevice(elapsedMs: number): void {
  record(["browser"], elapsedMs);
}

const finder = document.querySelector<HTMLElement>("#finder");
if (finder) mountProjectFinder(finder, { onMatched: recordOnDevice });

const chat = document.querySelector<HTMLElement>("#chat");
if (chat) mountChat(chat, { onAnswered: recordRoundTrip });

const contact = document.querySelector<HTMLElement>("#contact");
if (contact) mountContact(contact);

mountMotion();
