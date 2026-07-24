#!/usr/bin/env bash
#
# Deploy the FastAPI backend to the Oracle Ampere A1 VM.
#
# Runs from the dev machine. Syncs backend/ to the VM over SSH, builds a venv,
# rebuilds the vector store, installs the systemd unit and nginx site, and
# (re)starts the service. Idempotent: safe to run repeatedly.
#
# This is the FIRST-DEPLOY / manual path. Phase 7 replaces it with a
# path-filtered GitHub Actions pipeline; until then this is how the backend
# reaches the VM, straight from local commits without a push.
#
# Usage:   ./deploy.sh [user@]host
#          VM_HOST=ubuntu@<vm-ip> ./deploy.sh
#          SSH_KEY=~/.ssh/oracle ./deploy.sh ubuntu@<vm-ip>
#
# The secrets file /etc/ai-portfolio.env must already exist on the VM and be
# populated (see the runbook). This script never transports or echoes a secret;
# it refuses to start the service if that file is missing or empty.
#
set -euo pipefail

# --- Configuration ----------------------------------------------------------

readonly APP_USER="aiportfolio"
readonly APP_HOME="/opt/ai-portfolio"
readonly APP_ENV_FILE="/etc/ai-portfolio.env"
readonly PYTHON="python3.12"
readonly STAGE="/tmp/ai-portfolio-stage"
readonly SERVICE="ai-portfolio"

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
readonly HERE
readonly BACKEND="${HERE}/../backend"
readonly UNIT_SRC="${HERE}/systemd/${SERVICE}.service"
readonly NGINX_SRC="${HERE}/nginx/${SERVICE}.conf"

TARGET="${1:-${VM_HOST:-}}"
[[ -n ${TARGET} ]] || {
  printf 'usage: %s [user@]host   (or set VM_HOST)\n' "$0" >&2
  exit 2
}
[[ ${TARGET} == *@* ]] || TARGET="ubuntu@${TARGET}"

# Optional explicit key. Empty means "use the ssh-agent / default identity".
SSH_KEY="${SSH_KEY:-}"
ssh_opts=(-o StrictHostKeyChecking=accept-new)
[[ -n ${SSH_KEY} ]] && ssh_opts+=(-i "${SSH_KEY}")

# --- Output helpers ---------------------------------------------------------

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '    \033[0;32mok\033[0m %s\n' "$*"; }
die()  { printf '\n\033[0;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# SC2029: client-side expansion is intended — the remote command strings
# deliberately interpolate this machine's config vars (APP_HOME, PYTHON, ...)
# before they run on the VM. Used for the non-conditional remote calls; the
# reachability guards below invoke ssh directly to stay clear of SC2310.
# shellcheck disable=SC2029
remote() { ssh "${ssh_opts[@]}" "${TARGET}" "$@"; }

# --- Preflight --------------------------------------------------------------

command -v rsync >/dev/null 2>&1 || die "rsync is required on this machine"
command -v ssh   >/dev/null 2>&1 || die "ssh is required on this machine"
[[ -d ${BACKEND}    ]] || die "backend/ not found at ${BACKEND}"
[[ -f ${UNIT_SRC}   ]] || die "systemd unit not found at ${UNIT_SRC}"
[[ -f ${NGINX_SRC}  ]] || die "nginx config not found at ${NGINX_SRC}"

log "Deploying to ${TARGET}"
ssh "${ssh_opts[@]}" "${TARGET}" true || die "cannot SSH to ${TARGET} — check the host, user and key"
ok "SSH reachable"

# rsync must exist on the VM too. It is not in setup.sh's package set, so ensure
# it here — one guarded apt call, a no-op after the first deploy.
if ! ssh "${ssh_opts[@]}" "${TARGET}" "command -v rsync >/dev/null 2>&1"; then
  log "Installing rsync on the VM"
  ssh "${ssh_opts[@]}" "${TARGET}" "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq rsync" \
    || die "could not install rsync on the VM"
  ok "rsync installed"
fi

# --- 1. Sync code to a staging area -----------------------------------------
#
# Into a staging dir owned by the login user first, then moved into place under
# the service account by the remote block. rsync straight into a root-owned,
# aiportfolio-owned tree would need --rsync-path=sudo gymnastics; staging is
# simpler and the copy into place is a single guarded step.

log "Syncing backend/ to ${STAGE}"
remote "mkdir -p ${STAGE}"
rsync -az --delete \
  --exclude '.venv/' \
  --exclude '.env' \
  --exclude '.env.example' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '*.pyc' \
  --exclude 'data/*.db' \
  --exclude 'data/*.sqlite*' \
  --exclude 'test/*.log' \
  -e "ssh ${ssh_opts[*]}" \
  "${BACKEND}/" "${TARGET}:${STAGE}/backend/"
ok "code synced"

# The unit and nginx config travel alongside the code.
rsync -az -e "ssh ${ssh_opts[*]}" "${UNIT_SRC}"  "${TARGET}:${STAGE}/${SERVICE}.service"
rsync -az -e "ssh ${ssh_opts[*]}" "${NGINX_SRC}" "${TARGET}:${STAGE}/${SERVICE}.conf"
ok "unit and nginx config staged"

# --- 2. Provision on the VM -------------------------------------------------
#
# One sudo bash block. Everything up to the service start is safe without
# secrets — code, venv, dependencies, the vector store, the unit and nginx are
# all installed regardless. The env-file guard sits immediately before start,
# so a deploy run before the secrets are in place stages everything and stops
# with a clear instruction rather than booting a keyless service.

log "Provisioning on the VM (venv, ingest, unit, nginx, start)"

remote "sudo APP_USER='${APP_USER}' APP_HOME='${APP_HOME}' APP_ENV_FILE='${APP_ENV_FILE}' \
             PYTHON='${PYTHON}' STAGE='${STAGE}' SERVICE='${SERVICE}' bash -seuo pipefail" <<'REMOTE'
say() { printf '    \033[0;32mok\033[0m %s\n' "$*"; }
step() { printf '\n\033[1;36m  ->\033[0m %s\n' "$*"; }

BACKEND_DIR="${APP_HOME}/backend"
VENV="${APP_HOME}/venv"
HF_CACHE="${APP_HOME}/hf-cache"

# 2a. Move code into place under the service account.
step "installing code to ${BACKEND_DIR}"
mkdir -p "${BACKEND_DIR}"
rsync -a --delete \
  --exclude 'data/*.db' --exclude 'data/*.sqlite*' \
  "${STAGE}/backend/" "${BACKEND_DIR}/"
mkdir -p "${BACKEND_DIR}/data" "${HF_CACHE}"
chown -R "${APP_USER}:${APP_USER}" "${APP_HOME}"
say "code in place, owned by ${APP_USER}"

# 2b. Virtualenv + runtime dependencies (NOT the dev set).
step "building venv and installing dependencies"
if [[ ! -x "${VENV}/bin/python" ]]; then
  sudo -u "${APP_USER}" "${PYTHON}" -m venv "${VENV}"
  say "created venv"
fi
sudo -u "${APP_USER}" "${VENV}/bin/pip" install --quiet --upgrade pip
sudo -u "${APP_USER}" "${VENV}/bin/pip" install --quiet -r "${BACKEND_DIR}/requirements.txt"
say "dependencies installed"

# 2c. Rebuild the vector store from the markdown corpus (decision 27). Needs the
# embedding model but no secrets, so it runs here regardless of the env file.
step "rebuilding the vector store"
sudo -u "${APP_USER}" env HF_HOME="${HF_CACHE}" \
  bash -c "cd '${BACKEND_DIR}' && '${VENV}/bin/python' -m app.ingest"
say "vector store rebuilt"

# 2d. systemd unit.
step "installing the systemd unit"
install -m 644 "${STAGE}/${SERVICE}.service" "/etc/systemd/system/${SERVICE}.service"
systemctl daemon-reload
say "unit installed and daemon reloaded"

# 2e. nginx site — replace the default.
step "installing the nginx site"
install -m 644 "${STAGE}/${SERVICE}.conf" "/etc/nginx/sites-available/${SERVICE}"
ln -sf "/etc/nginx/sites-available/${SERVICE}" "/etc/nginx/sites-enabled/${SERVICE}"
rm -f /etc/nginx/sites-enabled/default
if nginx -t 2>/dev/null; then
  systemctl reload nginx
  say "nginx configured and reloaded"
else
  nginx -t || true
  echo "ERROR: nginx config test failed — leaving the running config untouched" >&2
  exit 1
fi

# 2f. Guard: the service will not start without its secrets.
step "checking the environment file"
if [[ ! -s "${APP_ENV_FILE}" ]] || ! grep -q '^ANTHROPIC_API_KEY=' "${APP_ENV_FILE}"; then
  cat >&2 <<GUARD

  ${APP_ENV_FILE} is missing or has no ANTHROPIC_API_KEY.

  Everything else is deployed. Populate the env file, then re-run deploy.sh:

    sudo install -m 640 -o root -g ${APP_USER} /dev/null ${APP_ENV_FILE}
    sudo tee ${APP_ENV_FILE} >/dev/null   # paste the vars, then Ctrl-D

  Required: ANTHROPIC_API_KEY, RESEND_API_KEY, CONTACT_NOTIFY_TO, SENTRY_DSN,
            AI_PORTFOLIO_ENV=production
GUARD
  exit 3
fi
say "environment file present"

# 2g. Start (or restart) the service.
step "starting the service"
systemctl enable --quiet "${SERVICE}"
systemctl restart "${SERVICE}"
sleep 2
if systemctl is-active --quiet "${SERVICE}"; then
  say "${SERVICE} is active"
else
  echo "ERROR: ${SERVICE} failed to start. Recent log:" >&2
  journalctl -u "${SERVICE}" -n 30 --no-pager >&2 || true
  exit 1
fi

# 2h. Local health check, direct and through nginx.
step "smoke-testing /health on the VM"
if curl -fsS --max-time 10 http://127.0.0.1:8000/health >/dev/null; then
  say "uvicorn answers on 127.0.0.1:8000"
else
  echo "ERROR: uvicorn did not answer /health" >&2
  exit 1
fi
if curl -fsS --max-time 10 http://127.0.0.1/health >/dev/null; then
  say "nginx proxies /health on port 80"
else
  echo "ERROR: nginx did not proxy /health" >&2
  exit 1
fi
REMOTE

ok "provisioning complete"

# --- 3. Done ----------------------------------------------------------------

host_only="${TARGET#*@}"
log "Deployed"
printf '    Verify from your own machine:  curl -i http://%s/health\n' "${host_only}"
printf '    Full smoke test (real Claude call + real email):\n'
printf '      ./smoke-remote.sh --all http://%s\n\n' "${host_only}"
