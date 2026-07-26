#!/usr/bin/env bash
#
# Run the full backend test suite on Linux.
#
# sqlite-vec has no Windows ARM64 wheel, so retrieval tests cannot run natively
# on the dev machine. Running `pytest` there still works — those tests skip —
# but this is what must pass before a step is presented for verification.
#
# Usage:  ./run-tests.sh [pytest args...]
# Requires: docker
#
set -euo pipefail

readonly IMAGE="ai-portfolio-backend-test:latest"
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
readonly HERE
readonly BACKEND="${HERE}/.."

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
# Plain progress, not -q. Installing torch takes minutes on first build, and a
# silent build is indistinguishable from a hung one.
docker build --progress=plain \
  -f "$(hostpath "${HERE}/Dockerfile")" \
  -t "${IMAGE}" \
  "$(hostpath "${BACKEND}")"

printf '\n\033[1;34m==>\033[0m Running backend test suite (linux/arm64)\n'
# Source is mounted rather than copied so edits take effect without a rebuild.
# The image is only rebuilt when requirements change.
docker run --rm \
  -v "$(hostpath "${BACKEND}")":/app \
  -w /app \
  "${IMAGE}" \
  python -m pytest "$@"
