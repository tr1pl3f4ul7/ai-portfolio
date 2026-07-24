#!/usr/bin/env bash
#
# Boot-test the systemd unit before it is ever deployed to the VM.
#
# Reproduces the VM's exact layout in an Ubuntu 24.04 systemd container — the
# aiportfolio service account, /opt/ai-portfolio/{backend,venv,hf-cache}, and a
# dummy /etc/ai-portfolio.env — then starts the REAL infra/systemd unit file and
# asserts the service comes up and answers /health as a non-root user.
#
# Deliberately a LIGHT venv: fastapi, uvicorn, pydantic, email-validator,
# python-dotenv, and nothing else. Importing app.main and serving /health does
# not touch torch, sentence-transformers or sqlite-vec — those are imported
# lazily on the first /chat request — so the heavy stack is not needed to prove
# the unit boots. Full dependency resolution is already covered by the backend
# test image; this test is about the unit file.
#
# Usage:  ./verify-unit.sh
# Requires: docker
#
set -euo pipefail

readonly IMAGE="ai-portfolio-setup-test:24.04"
readonly CONTAINER="ai-portfolio-unit-test"
readonly APP_USER="aiportfolio"
readonly APP_HOME="/opt/ai-portfolio"
readonly ENV_FILE="/etc/ai-portfolio.env"
readonly SERVICE="ai-portfolio"

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
readonly HERE
# This script lives in infra/test/, so the repo's backend/ is two levels up.
readonly BACKEND="${HERE}/../../backend"
readonly UNIT="${HERE}/../systemd/${SERVICE}.service"

if command -v cygpath >/dev/null 2>&1; then
  hostpath() { cygpath -w "$1"; }
  export MSYS_NO_PATHCONV=1
else
  hostpath() { printf '%s' "$1"; }
fi

pass() { printf '\033[0;32mPASS\033[0m %s\n' "$*"; }
fail() { printf '\033[0;31mFAIL\033[0m %s\n' "$*" >&2; }
step() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

[[ -f ${UNIT} ]] || { fail "unit file not found at ${UNIT}"; exit 1; }
[[ -d ${BACKEND}/app ]] || { fail "backend/app not found at ${BACKEND}/app"; exit 1; }

cleanup() { docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true; }
trap cleanup EXIT

dexec() { docker exec "${CONTAINER}" "$@"; }

step "Building systemd test image"
docker build -q -t "${IMAGE}" "$(hostpath "${HERE}")" >/dev/null

step "Starting container (systemd as PID 1)"
cleanup
docker run -d --name "${CONTAINER}" \
  --privileged --cgroupns=host \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  "${IMAGE}" >/dev/null

state=""
for _ in $(seq 1 20); do
  state=$(dexec systemctl is-system-running 2>&1 || true)
  case "${state}" in running | degraded) break ;; esac
  sleep 3
done
[[ ${state} == running || ${state} == degraded ]] || { fail "systemd did not start (${state})"; exit 1; }
pass "systemd is ${state}"

failures=0

step "Installing Python and creating the service layout"
dexec bash -c "apt-get update -qq && apt-get install -y -qq python3.12-venv python3-pip curl" >/dev/null
# Mirror setup.sh: a system account with no login shell, owning the app tree.
dexec useradd --system --create-home --home-dir "${APP_HOME}" \
      --shell /usr/sbin/nologin "${APP_USER}"
dexec mkdir -p "${APP_HOME}/backend/data" "${APP_HOME}/hf-cache"

step "Copying backend/app in"
# Only the package is needed to boot and serve /health — not the venv, the
# vector store or the tests.
docker cp "$(hostpath "${BACKEND}/app")" "${CONTAINER}:${APP_HOME}/backend/app"

step "Building the light venv"
dexec bash -c "python3.12 -m venv '${APP_HOME}/venv' \
  && '${APP_HOME}/venv/bin/pip' install --quiet --upgrade pip \
  && '${APP_HOME}/venv/bin/pip' install --quiet \
       fastapi==0.115.6 uvicorn==0.34.0 email-validator==2.3.0 python-dotenv==1.2.2" >/dev/null
dexec chown -R "${APP_USER}:${APP_USER}" "${APP_HOME}"
pass "venv built and tree owned by ${APP_USER}"

step "Writing a dummy environment file"
# Obvious non-secrets. The unit requires this file to exist; the app never makes
# a real API call in this test because /health touches nothing downstream.
dexec bash -c "cat > '${ENV_FILE}' <<'ENV'
ANTHROPIC_API_KEY=sk-ant-api03-UNIT-TEST-NOT-REAL
RESEND_API_KEY=re_UNIT_TEST_NOT_REAL
CONTACT_NOTIFY_TO=nobody@example.com
AI_PORTFOLIO_ENV=unit-test
ENV
chown root:${APP_USER} '${ENV_FILE}' && chmod 640 '${ENV_FILE}'"

step "Statically verifying the unit file"
docker cp "$(hostpath "${UNIT}")" "${CONTAINER}:/etc/systemd/system/${SERVICE}.service"
# systemd-analyze verify catches malformed directives and bad references before
# a start is ever attempted. It may warn about the nologin shell; that is
# expected for a service account and not a failure.
if dexec systemd-analyze verify "/etc/systemd/system/${SERVICE}.service" 2>&1 \
     | grep -vE "Command.*nologin|Executable.*nologin" | grep -qiE "error|failed"; then
  fail "systemd-analyze verify reported an error"
  dexec systemd-analyze verify "/etc/systemd/system/${SERVICE}.service" || true
  failures=$((failures + 1))
else
  pass "unit file verifies clean"
fi

step "Starting the service"
dexec systemctl daemon-reload
if dexec systemctl start "${SERVICE}"; then
  sleep 3
  if dexec systemctl is-active --quiet "${SERVICE}"; then
    pass "${SERVICE} is active"
  else
    fail "${SERVICE} did not stay active"
    dexec journalctl -u "${SERVICE}" -n 30 --no-pager || true
    failures=$((failures + 1))
  fi
else
  fail "${SERVICE} failed to start"
  dexec journalctl -u "${SERVICE}" -n 30 --no-pager || true
  failures=$((failures + 1))
fi

step "Checking /health through the service"
health=$(dexec bash -c "curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8000/health || echo FAILED" | tr -d '\r')
if [[ ${health} == "200" ]]; then
  pass "/health returned 200"
else
  fail "/health returned '${health}'"
  failures=$((failures + 1))
fi

body=$(dexec bash -c "curl -s --max-time 10 http://127.0.0.1:8000/health || true" | tr -d '\r')
if [[ ${body} == '{"status":"ok"}' ]]; then
  pass "/health body is the expected contract"
else
  fail "/health body was '${body}'"
  failures=$((failures + 1))
fi

step "Asserting the service runs as ${APP_USER}, not root"
run_user=$(dexec bash -c "ps -o user= -p \$(systemctl show -p MainPID --value ${SERVICE})" | tr -d '\r ' )
if [[ ${run_user} == "${APP_USER}" ]]; then
  pass "process runs as ${run_user}"
else
  fail "process runs as '${run_user}', expected ${APP_USER}"
  failures=$((failures + 1))
fi

step "Asserting the unit will not start without its env file"
# Removing the secrets file must stop the service from starting — the guard that
# turns a missing key into a clean boot failure rather than a runtime surprise.
dexec systemctl stop "${SERVICE}"
dexec mv "${ENV_FILE}" "${ENV_FILE}.bak"
if dexec systemctl start "${SERVICE}" 2>/dev/null; then
  fail "service started with no env file — EnvironmentFile guard is not working"
  failures=$((failures + 1))
  dexec systemctl stop "${SERVICE}" || true
else
  pass "service correctly refused to start without ${ENV_FILE}"
fi
dexec mv "${ENV_FILE}.bak" "${ENV_FILE}"

echo
if [[ ${failures} -eq 0 ]]; then
  printf '\033[0;32mALL CHECKS PASSED\033[0m\n'
  exit 0
fi
printf '\033[0;31m%d CHECK(S) FAILED\033[0m\n' "${failures}"
exit 1
