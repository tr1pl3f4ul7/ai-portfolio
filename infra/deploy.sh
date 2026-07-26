#!/usr/bin/env bash
#
# Deploy the FastAPI backend to the Oracle Ampere A1 VM.
#
# Syncs backend/ to the VM over SSH, builds a venv, rebuilds the vector store,
# installs the systemd unit and nginx site, and (re)starts the service.
# Idempotent: safe to run repeatedly. Runs both from the dev machine (manual
# deploys) and from .github/workflows/backend-deploy.yml (CI) — same script,
# same steps, either way (decision 52).
#
# Usage:   ./deploy.sh [user@]host
#          VM_HOST=ubuntu@<vm-ip> ./deploy.sh
#          SSH_KEY=~/.ssh/oracle ./deploy.sh ubuntu@<vm-ip>
#
# The secrets file /etc/ai-portfolio.env normally already exists on the VM,
# populated once by hand (see the runbook) — this script never needed to touch
# it and still doesn't for a plain local run. In CI (CI=true, set automatically
# by GitHub Actions), it instead WRITES that file from this process's own
# environment (ANTHROPIC_API_KEY, RESEND_API_KEY, CONTACT_NOTIFY_TO,
# SENTRY_DSN — themselves sourced from GitHub Actions secrets by the workflow),
# so GitHub Secrets becomes the one place these values live and every deploy
# carries them through automatically. Piped over SSH via stdin, never as a
# command-line argument or an echoed value, and CI is required as well as the
# values themselves so a stray locally-exported ANTHROPIC_API_KEY (e.g. for
# unrelated testing) can never silently overwrite the VM's real env file.
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

# The code is pushed with tar over ssh, not rsync: Git Bash on Windows ships
# tar, scp and ssh but NOT rsync. rsync is still used VM-side for the copy into
# place (installed there below), where --delete matters; it just isn't needed
# on this machine.
command -v tar >/dev/null 2>&1 || die "tar is required on this machine"
command -v scp >/dev/null 2>&1 || die "scp is required on this machine"
command -v ssh >/dev/null 2>&1 || die "ssh is required on this machine"
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
# the service account by the remote block. Copying straight into a root-owned,
# aiportfolio-owned tree would need sudo gymnastics; staging is simpler and the
# copy into place is a single guarded step.
#
# The push is a tar stream over ssh rather than rsync — see the preflight note.
# Excludes: the venv, the secrets file, byte-compiled and cached files, the
# built vector store and any submissions database (rebuilt on the VM), and logs.
# .env in particular must never travel.

log "Syncing backend/ to ${STAGE}"
remote "rm -rf ${STAGE}/backend && mkdir -p ${STAGE}/backend"
tar czf - -C "${BACKEND}" \
  --exclude='.venv' \
  --exclude='.env*' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='*.pyc' \
  --exclude='*.db' \
  --exclude='*.sqlite*' \
  --exclude='*.log' \
  . | remote "tar xzf - -C ${STAGE}/backend"
ok "code synced"

# The unit and nginx config travel alongside the code.
scp "${ssh_opts[@]}" "${UNIT_SRC}"  "${TARGET}:${STAGE}/${SERVICE}.service"
scp "${ssh_opts[@]}" "${NGINX_SRC}" "${TARGET}:${STAGE}/${SERVICE}.conf"
ok "unit and nginx config staged"

# --- 1.5. CI-only: write the env file from this process's own secrets -------
#
# Local manual runs are untouched — CI must be "true" (set automatically by
# GitHub Actions, never by hand) AND every required var must be non-empty, so
# this can only ever fire from the real deploy workflow. Piped over SSH via
# stdin into a heredoc, never a command-line argument, so the values never
# appear in a process listing on either end; -o 640 root:aiportfolio matches
# what the manual runbook instructions already produce.

if [[ ${CI:-} == "true" ]]; then
  log "CI run detected — writing ${APP_ENV_FILE} from GitHub Actions secrets"
  for var in ANTHROPIC_API_KEY RESEND_API_KEY CONTACT_NOTIFY_TO SENTRY_DSN; do
    [[ -n ${!var:-} ]] || die "CI=true but \$${var} is empty — is it set in the workflow's env?"
  done
  remote "sudo install -m 640 -o root -g ${APP_USER} /dev/null ${APP_ENV_FILE} && sudo tee ${APP_ENV_FILE} >/dev/null" <<EOF
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
RESEND_API_KEY=${RESEND_API_KEY}
CONTACT_NOTIFY_TO=${CONTACT_NOTIFY_TO}
SENTRY_DSN=${SENTRY_DSN}
AI_PORTFOLIO_ENV=production
EOF
  ok "environment file written (values never logged)"
fi

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
if systemctl is-active --quiet "${SERVICE}"; then
  say "${SERVICE} is active"
else
  echo "ERROR: ${SERVICE} failed to start. Recent log:" >&2
  journalctl -u "${SERVICE}" -n 30 --no-pager >&2 || true
  exit 1
fi

# 2h. Local health check, direct and through nginx.
#
# Poll rather than sleep-then-curl. The unit is Type=exec, so systemd reports
# the service active the moment uvicorn is exec'd — but the app loads the ~90 MB
# embedding model in its startup lifespan before it binds the port. A single
# immediate curl races that and reports a false failure on a service that is
# fine.
#
# The budget is generous on purpose: measured at 69s on the Ampere A1 with a
# cold page cache, against an earlier 40s ceiling that failed the deploy while
# the service was still starting correctly. Warm restarts take a few seconds;
# this only costs wall-clock when something is genuinely wrong.
step "waiting for /health on 127.0.0.1:8000 (model load can take ~70s cold)"
health_ok=false
for _ in $(seq 1 90); do
  if curl -fsS --max-time 5 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    health_ok=true
    break
  fi
  # Bail early if the service died while we were waiting.
  systemctl is-active --quiet "${SERVICE}" || break
  sleep 2
done
if [[ ${health_ok} == true ]]; then
  say "uvicorn answers on 127.0.0.1:8000"
else
  echo "ERROR: uvicorn did not answer /health within the timeout. Recent log:" >&2
  journalctl -u "${SERVICE}" -n 30 --no-pager >&2 || true
  exit 1
fi

# Port 80 now redirects to 443 (Step 5.2) rather than proxying directly, so a
# plain http:// check here would just follow a redirect and report success
# without ever exercising nginx's real path. --resolve keeps the request
# local while still sending the Host/SNI the certificate was issued for.
#
# -k is deliberate, not laziness: nginx presents the Cloudflare Origin CA
# certificate (decision 49), which only Cloudflare's edge is meant to trust —
# no system CA bundle validates it, so a plain curl here would always fail on
# a correctly-configured deploy. This check's job is "does nginx terminate
# TLS and proxy to uvicorn," not "is the cert publicly trusted" — that's what
# the workflow's separate post-deploy smoke test already verifies, against
# the real public domain through Cloudflare's actual edge, with real trust
# validation and no -k.
if curl -fsSk --max-time 10 --resolve api.ljubenvassilev.com:443:127.0.0.1 \
     https://api.ljubenvassilev.com/health >/dev/null; then
  say "nginx proxies /health on port 443"
else
  echo "ERROR: nginx did not proxy /health over TLS" >&2
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
