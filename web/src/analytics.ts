/**
 * Product analytics — autocapture plus the three explicit events named in
 * web/CLAUDE.md: form submitted, chat used, project finder used.
 *
 * Off without a key, same reasoning as observability.ts: nothing imports
 * main.ts in a test, so this never actually runs during `vitest run`
 * regardless of what a local .env contains.
 *
 * Loaded with a dynamic `import()`, same reasoning as observability.ts —
 * analytics has no business delaying the first thing a visitor sees.
 */

let posthog: typeof import("posthog-js").default | null = null;

/** Returns whether PostHog was actually initialised, for the caller to log or ignore. */
export async function initAnalytics(): Promise<boolean> {
  const key = import.meta.env.VITE_POSTHOG_KEY;
  if (!key) return false;

  posthog = (await import("posthog-js")).default;
  posthog.init(key, {
    api_host: import.meta.env.VITE_POSTHOG_HOST || "https://us.i.posthog.com",
  });
  return true;
}

/** No-ops before init (or without a key) rather than queuing or throwing. */
export function track(event: string, properties?: Record<string, unknown>): void {
  posthog?.capture(event, properties);
}
