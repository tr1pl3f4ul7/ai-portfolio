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
