/**
 * Turnstile widget, wrapped so the contact form doesn't have to know about it.
 *
 * The script is loaded from `index.html` with `render=explicit`, because the
 * contact form is built in JS (`contact.ts`) rather than present in the markup
 * — Turnstile's automatic mode scans the DOM on load and would find nothing.
 *
 * Deliberately DOM-light and dependency-injected so `contact.ts` stays testable
 * without loading a third-party script into jsdom.
 */

import { TURNSTILE_SITE_KEY } from "./config";

/** The subset of Turnstile's API this uses. */
export interface TurnstileApi {
  render(container: HTMLElement, options: Record<string, unknown>): string;
  reset(widgetId: string): void;
  remove(widgetId: string): void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

/** How long to wait for the third-party script before giving up on it. */
const SCRIPT_TIMEOUT_MS = 10_000;
const POLL_MS = 50;

/**
 * Resolve once `window.turnstile` exists, or null if it never turns up.
 *
 * Polling rather than the script's `onload` callback: the callback fires once,
 * globally, and may well have fired before this module ran. Checking for the
 * object is idempotent and works whenever it is called.
 *
 * Null rather than throwing — a blocked or slow third-party script is a
 * plausible Tuesday, and the form degrades to submitting without a token
 * rather than becoming unusable. The Worker decides what that is worth.
 */
export function whenReady(
  win: Window = window,
  timeoutMs: number = SCRIPT_TIMEOUT_MS,
): Promise<TurnstileApi | null> {
  if (win.turnstile) return Promise.resolve(win.turnstile);

  return new Promise((resolve) => {
    const startedAt = Date.now();
    const timer = win.setInterval(() => {
      if (win.turnstile) {
        win.clearInterval(timer);
        resolve(win.turnstile);
      } else if (Date.now() - startedAt >= timeoutMs) {
        win.clearInterval(timer);
        resolve(null);
      }
    }, POLL_MS);
  });
}

export interface Widget {
  /** The current token, or null if the challenge has not completed. */
  token(): string | null;
  /** Discard the used token and issue a fresh challenge. */
  reset(): void;
}

/**
 * Render the widget into `container` and hand back a handle to it.
 *
 * Returns a null-token handle if Turnstile never loaded, so callers have one
 * shape to deal with either way.
 */
export async function mountWidget(
  container: HTMLElement,
  win: Window = window,
): Promise<Widget> {
  const api = await whenReady(win);
  if (!api) return { token: () => null, reset: () => {} };

  let token: string | null = null;

  const widgetId = api.render(container, {
    sitekey: TURNSTILE_SITE_KEY,
    // Invisible for most visitors; only shows an interactive challenge when
    // Cloudflare is unsure. The contact form is not the place to make everyone
    // click a box.
    appearance: "interaction-only",
    // Tokens are single-use and expire. Clearing on both means the form never
    // submits one that is already spent — the commonest cause of a mystifying
    // "verification failed" on a form left open in a tab.
    callback: (issued: string) => {
      token = issued;
    },
    "expired-callback": () => {
      token = null;
    },
    "error-callback": () => {
      token = null;
    },
  });

  return {
    token: () => token,
    reset: () => {
      token = null;
      api.reset(widgetId);
    },
  };
}
