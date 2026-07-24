// From vitest/config, not vite — it is the same defineConfig widened to accept
// the `test` block below.
import { defineConfig } from "vitest/config";

// Where `npm run dev` proxies API calls. Overridable so the page can be
// developed against a local backend instead of the live VM:
//
//   DEV_API_TARGET=http://127.0.0.1:8000 npm run dev
//
// A public IP, not a secret. In production the page is built with
// VITE_API_BASE_URL pointing at the real backend origin and no proxy is used.
const DEV_API_TARGET = process.env.DEV_API_TARGET ?? "http://140.238.207.203";

export default defineConfig({
  server: {
    // Proxying in development means the browser makes a same-origin request, so
    // there is no CORS preflight and the dev path exercises the same relative
    // URLs the built site uses. `/api/chat` here reaches `/chat` on the backend.
    proxy: {
      "/api": {
        target: DEV_API_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },

  build: {
    // The page must be fast before any model loads — see web/CLAUDE.md. Fail the
    // build loudly if a dependency ever pushes the bundle past a sane size.
    chunkSizeWarningLimit: 150,
  },

  test: {
    // The widgets are DOM code; test them against a DOM.
    environment: "jsdom",
    include: ["test/**/*.test.ts"],
    restoreMocks: true,
  },
});
