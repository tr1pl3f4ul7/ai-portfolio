#!/usr/bin/env bash
#
# Run the full backend test suite on Linux.
#
# sqlite-vec has no wheel matching the local environment, so retrieval tests
# cannot run natively here. Running `pytest` locally still works — those
# tests skip — but this is what must pass before a step is presented for
# verification.
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

# Source is mounted rather than copied so edits take effect without a rebuild.
# The image is only rebuilt when requirements change.
run_in_container() {
  docker run --rm \
    -v "$(hostpath "${BACKEND}")":/app \
    -w /app \
    "${IMAGE}" \
    "$@"
}

# The same checks as .github/workflows/backend-ci.yml, in the same order, so a
# green run here means what CI means by it. `.` rather than a file list, matching
# CI exactly — a lint error under test/ is still a lint error.
#
# EXE002 is ignored here and ONLY here. The rule flags a file that is executable
# without a shebang, and the bind mount above presents every file from the
# Windows host to Linux as 0777 — so it fires on all 38 Python files, none of
# which is executable in git or in a CI checkout. Ignoring it is what makes this
# run agree with CI rather than diverge from it; CI runs the rule unignored on a
# real checkout, so a genuinely executable .py would still be caught there.
printf '\n\033[1;34m==>\033[0m Linting\n'
run_in_container python -m ruff check . --ignore EXE002

printf '\n\033[1;34m==>\033[0m Running backend test suite (linux/arm64)\n'
run_in_container python -m pytest "$@"
