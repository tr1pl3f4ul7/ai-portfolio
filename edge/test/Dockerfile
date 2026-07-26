# Linux test environment for the edge Worker.
#
# workerd — the runtime wrangler and @cloudflare/vitest-pool-workers both
# shell out to — publishes no Windows ARM64 build at all ("Unsupported
# platform: win32 arm64 LE"). Rather than split the stack between dev and
# production, the whole edge test suite runs here — on linux/arm64, the same
# pattern backend/test/Dockerfile already uses for sqlite-vec.
FROM node:24-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

CMD ["npm", "test"]
