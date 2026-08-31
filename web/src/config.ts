/**
 * Runtime configuration.
 *
 * The backend origin is configuration, never a literal scattered through the
 * source — see web/CLAUDE.md.
 *
 * Development: both unset, so calls go to `/api/...` and Vite proxies them to
 * the VM (see vite.config.ts), bypassing the edge Worker entirely for a
 * simpler local loop. Same-origin, so no CORS preflight.
 *
 * Production: VITE_API_BASE_URL is the backend origin directly (chat).
 * VITE_CONTACT_BASE_URL is the edge Worker's own domain (contact) — a
 * separate hostname from the backend on purpose, so the Worker's internal
 * forward to the real /contact can never re-trigger itself (decision 48).
 */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "/api";
export const CONTACT_BASE_URL: string = import.meta.env.VITE_CONTACT_BASE_URL ?? "/api";

/** Longest a visitor waits before we give up on a request. */
export const REQUEST_TIMEOUT_MS = 60_000;

/**
 * Turnstile site key for the contact form.
 *
 * Public by design — it ships in the page source and identifies the widget, not
 * the account. The half that must stay secret is TURNSTILE_SECRET_KEY, which
 * lives only in the edge Worker (`wrangler secret put`) and never here.
 *
 * Hardcoded rather than read from an env var, unlike the origins above: those
 * differ between dev and production, this does not. Cloudflare pairs the key
 * with a hostname allowlist, so the same key is correct everywhere and a build
 * that forgot to set it would silently ship a form nobody can submit.
 */
export const TURNSTILE_SITE_KEY = "0x4AAAAAAEjCCmr_8MCC-16C";
