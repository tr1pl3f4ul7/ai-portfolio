#!/usr/bin/env bash
#
# Run the edge Worker's test suite on Linux.
#
# workerd has no build matching the local environment, so `npm install` and
# `vitest` cannot run natively here at all (not even a partial/skipping run,
# unlike backend's sqlite-vec gap). This is what must pass before a step is
# presented for verification.
#
# Usage:  ./run-tests.sh [vitest args...]
# Requires: docker
#
set -euo pipefail

readonly IMAGE="ai-portfolio-edge-test:latest"
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
readonly HERE
readonly EDGE="${HERE}/.."

# Git Bash rewrites Unix-looking paths into Windows paths before handing them to
# a native binary, mangling container-side paths. Suppress it and convert host
# paths explicitly. No-ops on Linux and macOS.
if command -v cygpath >/dev/null 2>&1; then
  hostpath() { cygpath -w "$1"; }
  export MSYS_NO_PATHCONV=1
else
  hostpath() { printf '%s' "$1"; }
fi

printf '\n\033[1;34m==>\033[0m Building test image\n'
docker build --progress=plain \
  -f "$(hostpath "${HERE}/Dockerfile")" \
  -t "${IMAGE}" \
  "$(hostpath "${EDGE}")"

# Source is mounted rather than copied so edits take effect without a rebuild.
# node_modules stays inside the image (workerd's binary is linux/arm64; a bind
# mount would shadow it with whatever — or nothing — is on the host).
run_in_container() {
  docker run --rm \
    -v "$(hostpath "${EDGE}")":/app \
    -v /app/node_modules \
    -w /app \
    "${IMAGE}" \
    "$@"
}

# The same checks as .github/workflows/edge-ci.yml, in the same order, so a green
# run here means what CI means by it. Typechecking is not redundant with the
# tests: vitest transpiles TypeScript without checking it, so the suite cannot
# catch a type error at all — which is exactly how two of them reached a commit.
printf '\n\033[1;34m==>\033[0m Typechecking\n'
run_in_container npm run typecheck

printf '\n\033[1;34m==>\033[0m Running edge test suite (linux/arm64)\n'
run_in_container npx vitest run "$@"
