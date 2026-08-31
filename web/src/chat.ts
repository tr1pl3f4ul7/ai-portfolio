/**
 * The chat widget — layers three and four of the architecture, live.
 *
 * A question goes to the VM, which embeds it, searches a local vector store,
 * and asks the hosted model to answer from what it retrieved. The widget shows the real
 * round-trip time and the sections the answer was grounded in, because that
 * evidence is the point of the page.
 *
 * It does NOT fake token-by-token streaming. The endpoint returns a complete
 * response, and animating a reveal would imply an architecture that isn't
 * there — on a page whose whole argument is that the numbers are real.
 */

import { ApiError, askQuestion, type Source } from "./api";

const PLACEHOLDER = "Ask about my work…";

/**
 * Strip markdown emphasis from an answer.
 *
 * The system prompt asks for plain prose, and mostly gets it — but models reach
 * for `**bold**` on proper nouns often enough that a visitor would see literal
 * asterisks. A prompt is a request; this is the guarantee. Rendering the
 * markdown instead would mean parsing model output into HTML, which is a much
 * larger surface than this page needs.
 */
export function toPlainText(answer: string): string {
  return answer
    .replace(/\*\*(.+?)\*\*/gs, "$1")
    .replace(/__(.+?)__/gs, "$1")
    .replace(/^#{1,6}\s+/gm, "");
}

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

function renderSources(sources: Source[]): HTMLElement {
  const wrap = el("div", "chat-sources");
  wrap.append(el("span", "chat-sources-label", "grounded in"));
  for (const source of sources) {
    wrap.append(el("span", "chat-source", `${source.document} · ${source.section}`));
  }
  return wrap;
}

/** One exchange in the transcript.
 *
 * An exchange can be resolved or rejected more than once, because a rejected
 * one can be retried in place — the visitor's question stays where it was in
 * the transcript rather than being re-asked as a new entry, which would read as
 * though they had typed it twice.
 */
interface Exchange {
  node: HTMLElement;
  resolve: (answer: string, sources: Source[], elapsedMs: number) => void;
  /** `onRetry` is omitted when retrying could not possibly help. */
  reject: (message: string, onRetry?: () => void) => void;
}

function renderExchange(question: string): Exchange {
  const node = el("div", "chat-exchange");
  node.append(el("p", "chat-question", question));

  const showPending = (): void => {
    node.append(el("p", "chat-pending", "retrieving…"));
  };

  /** Clear whatever the last attempt left behind, so a retry starts clean. */
  const clearAttempt = (): void => {
    for (const stale of node.querySelectorAll(".chat-pending, .chat-error, .chat-retry")) {
      stale.remove();
    }
  };

  showPending();

  return {
    node,
    resolve(answer, sources, elapsedMs) {
      clearAttempt();
      node.append(el("p", "chat-answer", toPlainText(answer)));
      if (sources.length > 0) node.append(renderSources(sources));
      // The measured round trip: the VM's retrieval plus the model call.
      node.append(el("p", "chat-timing", `server + cloud · ${(elapsedMs / 1000).toFixed(2)}s`));
    },
    reject(message, onRetry) {
      clearAttempt();
      node.append(el("p", "chat-error", message));
      if (!onRetry) return;

      const retry = el("button", "chat-retry", "try again");
      retry.type = "button";
      retry.addEventListener("click", () => {
        clearAttempt();
        showPending();
        onRetry();
      });
      node.append(retry);
    },
  };
}

export interface ChatOptions {
  /**
   * Called with the measured round trip after a successful answer, so the
   * inference trace can show a real number for the server and cloud layers
   * instead of a placeholder.
   */
  onAnswered?: (elapsedMs: number) => void;
  /** From GET /content/ask (decision 57) — never hardcoded here. */
  suggestions?: string[];
}

export function mountChat(root: HTMLElement, options: ChatOptions = {}): void {
  root.replaceChildren();

  const transcript = el("div", "chat-transcript");
  // Answers arrive asynchronously; announce them to screen readers.
  transcript.setAttribute("aria-live", "polite");
  transcript.setAttribute("aria-busy", "false");

  const form = el("form", "chat-form");
  form.setAttribute("novalidate", "");

  const label = el("label", "sr-only", "Ask a question about Ljuben's work");
  label.htmlFor = "chat-input";

  const input = el("input", "chat-input");
  input.id = "chat-input";
  input.type = "text";
  input.placeholder = PLACEHOLDER;
  input.autocomplete = "off";
  input.maxLength = 1000; // Matches MAX_QUESTION_CHARS on the backend.

  const button = el("button", "chat-send", "ask");
  button.type = "submit";

  form.append(label, input, button);

  const suggestions = el("div", "chat-prompts");
  for (const prompt of options.suggestions ?? []) {
    const chip = el("button", "chat-prompt", prompt);
    chip.type = "button";
    chip.addEventListener("click", () => {
      input.value = prompt;
      form.requestSubmit();
    });
    suggestions.append(chip);
  }

  root.append(transcript, form, suggestions);

  let inFlight = false;

  const setBusy = (busy: boolean): void => {
    inFlight = busy;
    input.disabled = busy;
    button.disabled = busy;
    button.textContent = busy ? "…" : "ask";
    transcript.setAttribute("aria-busy", String(busy));
  };

  /**
   * Send one question and fill in its exchange. Separate from the submit
   * handler so a failed attempt can be re-run against the same exchange.
   *
   * The retry is offered, not automatic. The backend has already retried this
   * fourteen times before answering 503, so a client that quietly tried again
   * would be adding load to a tier that just said it was contended — and doing
   * it invisibly, on a page whose entire argument is that the numbers are real.
   */
  const ask = (question: string, exchange: Exchange): void => {
    setBusy(true);
    const started = performance.now();

    void askQuestion(question)
      .then((response) => {
        const elapsedMs = performance.now() - started;
        exchange.resolve(response.answer, response.sources, elapsedMs);
        options.onAnswered?.(elapsedMs);
      })
      .catch((error: unknown) => {
        const failure = error instanceof ApiError ? error : null;
        exchange.reject(
          failure?.message ?? "Something went wrong.",
          failure?.retryable ? () => ask(question, exchange) : undefined,
        );
      })
      .finally(() => {
        setBusy(false);
        input.focus();
      });
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (inFlight) return;

    const question = input.value.trim();
    if (!question) return;

    const exchange = renderExchange(question);
    transcript.append(exchange.node);
    input.value = "";

    ask(question, exchange);
  });
}
