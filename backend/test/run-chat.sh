#!/usr/bin/env bash
#
# Serve the backend from the Linux test container so /chat can be exercised by
# hand on the dev machine.
#
# sqlite-vec has no wheel matching the local environment, so the API cannot
# run natively here. This starts the same linux/arm64 image the test suite
# uses, publishing uvicorn on localhost:8000. Then, in another terminal:
#
#     python smoke_chat.py
#
# The Anthropic key is passed with --env-file, so it never appears in the
# command line, the shell history, or this script's output.
#
# Usage:  ./run-chat.sh
# Requires: docker, backend/.env containing ZAI_API_KEY
set -euo pipefail

readonly IMAGE="ai-portfolio-backend-test:latest"
readonly PORT="${PORT:-8000}"
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

if [ ! -f "${BACKEND}/.env" ]; then
  printf '\033[1;31mbackend/.env not found — it must contain ZAI_API_KEY\033[0m\n' >&2
  exit 1
fi

if [ ! -f "${BACKEND}/data/vectors.db" ]; then
  printf '\033[1;31mNo vector store. Build it first:\033[0m\n' >&2
  printf '  docker run --rm -v "%s":/app -w /app %s python -m app.ingest\n' \
    "$(hostpath "${BACKEND}")" "${IMAGE}" >&2
  exit 1
fi

printf '\n\033[1;34m==>\033[0m Building test image\n'
docker build --progress=plain \
  -f "$(hostpath "${HERE}/Dockerfile")" \
  -t "${IMAGE}" \
  "$(hostpath "${BACKEND}")"

printf '\n\033[1;34m==>\033[0m Serving on http://127.0.0.1:%s (ctrl-c to stop)\n' "${PORT}"
printf '\033[2mIn another terminal:  python %s/smoke_chat.py\033[0m\n\n' "${HERE}"

docker run --rm -it \
  -v "$(hostpath "${BACKEND}")":/app \
  -w /app \
  --env-file "$(hostpath "${BACKEND}/.env")" \
  -p "127.0.0.1:${PORT}:8000" \
  "${IMAGE}" \
  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
