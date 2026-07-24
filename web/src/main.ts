/**
 * Entry point. Mounts the widgets and the scroll reveals.
 *
 * Nothing here starts a model download or blocks first paint — the page must be
 * fast before any AI runs (web/CLAUDE.md). The on-device summariser arrives in
 * Step 3.3 and will be behind an explicit click.
 */

import { mountChat } from "./chat";
import { mountContact } from "./contact";
import { mountReveals } from "./reveal";

/**
 * Show a real measurement on the layers that just did the work.
 *
 * The chat exercises retrieval on the VM and generation at the Claude API, so
 * those two rows — and only those two — get the number. The browser and edge
 * rows stay as they are until something actually runs there.
 */
function recordRoundTrip(elapsedMs: number): void {
  const seconds = `${(elapsedMs / 1000).toFixed(2)}s`;
  for (const layer of ["server", "cloud"]) {
    const cost = document.querySelector<HTMLElement>(`[data-layer="${layer}"] [data-cost]`);
    if (!cost) continue;
    cost.textContent = seconds;
    cost.classList.add("is-measured");
  }
}

const chat = document.querySelector<HTMLElement>("#chat");
if (chat) mountChat(chat, { onAnswered: recordRoundTrip });

const contact = document.querySelector<HTMLElement>("#contact");
if (contact) mountContact(contact);

mountReveals();
