import { cloudflareTest } from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [
    cloudflareTest({
      wrangler: { configPath: "./wrangler.toml" },
      // Nothing here exercises the pool-injected env — every test builds its
      // own fake env and calls worker.fetch() directly (edge/CLAUDE.md keeps
      // classification pure and separately testable for exactly this reason).
      // Workers AI has no local simulation, so merely declaring [ai] in
      // wrangler.toml otherwise forces a live Cloudflare connection just to
      // start the pool, before a single test runs.
      remoteBindings: false,
    }),
  ],
});
