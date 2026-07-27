#!/usr/bin/env bash
#
# Run `wrangler dev` for local smoke testing — the plan's own required step
# before every deploy (edge/CLAUDE.md).
#
# workerd has no build matching the local environment (docs/decisions.md,
# decision 45), so this runs in the same Linux container test/Dockerfile
# builds, with the dev server's port forwarded to the host.
#
# Needs live Cloudflare credentials — Workers AI has no local simulation.
# Read from edge/.env if present (see .env.example for the shape and how to
# get them), otherwise from whatever is already exported in this shell. Either
# way, the values themselves are never echoed by this script.
#
# Usage:  ./dev.sh
# Requires: docker, CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID
#
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
readonly HERE

if [[ -f "${HERE}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${HERE}/.env"
  set +a
fi

if [[ -z "${CLOUDFLARE_API_TOKEN:-}" || -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]]; then
  echo "Set CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID, either in edge/.env" >&2
  echo "(copy .env.example) or exported in this shell — see .env.example for how" >&2
  echo "to get them." >&2
  exit 1
fi

readonly IMAGE="ai-portfolio-edge-test:latest"

if command -v cygpath >/dev/null 2>&1; then
  hostpath() { cygpath -w "$1"; }
  export MSYS_NO_PATHCONV=1
else
  hostpath() { printf '%s' "$1"; }
fi

printf '\n\033[1;34m==>\033[0m Building test image (shared with ./test/run-tests.sh)\n'
docker build --progress=plain \
  -f "$(hostpath "${HERE}/test/Dockerfile")" \
  -t "${IMAGE}" \
  "$(hostpath "${HERE}")"

printf '\n\033[1;34m==>\033[0m Starting wrangler dev on http://localhost:8787\n'
docker run --rm \
  -v "$(hostpath "${HERE}")":/app \
  -v /app/node_modules \
  -w /app \
  -p 8787:8787 \
  -e CLOUDFLARE_API_TOKEN \
  -e CLOUDFLARE_ACCOUNT_ID \
  "${IMAGE}" \
  npx wrangler dev --ip 0.0.0.0
