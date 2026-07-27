/**
 * Browser error and performance tracking.
 *
 * Mirrors backend/app/observability.py: off without a DSN, which is the
 * default on a dev machine and in CI. There's no equivalent here of the
 * backend's real incident (a live Sentry project catching test traffic
 * because `main.py` gets imported by every test through `TestClient`) —
 * nothing in this codebase imports main.ts, so `initSentry()` is only ever
 * called from a real page load, never from a test run, regardless of what a
 * local .env happens to contain.
 *
 * Loaded with a dynamic `import()` — Sentry's browser SDK with tracing is a
 * six-figure-byte dependency, and bundling it into the eagerly-loaded entry
 * script would repeat the exact mistake this project already ruled out
 * choosing a framework over (decision 40): every kilobyte here competes with
 * the on-device model download for the visitor's first paint.
 */

/** Returns whether Sentry was actually initialised, for the caller to log or ignore. */
export async function initSentry(): Promise<boolean> {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return false;

  const Sentry = await import("@sentry/browser");

  Sentry.init({
    dsn,
    // The DSN is write-only and this client sends no cookies or auth headers
    // of its own, but there's no reason to ask Sentry to collect more than
    // the default error/breadcrumb data either.
    sendDefaultPii: false,
    // A plain array here REPLACES Sentry's defaults rather than extending
    // them — silently dropping the global-handler integrations that catch
    // window.onerror and unhandled rejections in the first place. The
    // function form is the one that still gets them.
    integrations: (defaults) => [...defaults, Sentry.browserTracingIntegration()],
    tracesSampleRate: 0.1,
  });
  return true;
}

/**
 * Manually report an error a caller already caught and handled gracefully.
 *
 * Sentry's own global-handler integrations only catch uncaught throws and
 * unhandled rejections — a try/catch that shows a fallback UI instead of
 * crashing is, from Sentry's perspective, nothing happening at all. The
 * content fetch in main.ts is exactly that case: worth knowing about in
 * production, invisible without this.
 */
export async function reportError(error: unknown): Promise<void> {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return;

  const Sentry = await import("@sentry/browser");
  Sentry.captureException(error);
}
