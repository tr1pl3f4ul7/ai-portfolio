/**
 * Runtime configuration.
 *
 * The backend origin is configuration, never a literal scattered through the
 * source — see web/CLAUDE.md.
 *
 * Development: unset, so calls go to `/api/...` and Vite proxies them to the
 * VM (see vite.config.ts). Same-origin, so no CORS preflight.
 *
 * Production: built with VITE_API_BASE_URL pointing at the backend origin.
 */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "/api";

/** Longest a visitor waits before we give up on a request. */
export const REQUEST_TIMEOUT_MS = 60_000;
