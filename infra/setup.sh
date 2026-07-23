#!/usr/bin/env bash
#
# One-shot bootstrap for the Oracle Ampere A1 VM (Ubuntu 24.04, aarch64).
#
# Installs nginx, certbot, Python, and a dedicated service account, then opens
# the firewall for HTTP/HTTPS.
#
# SAFE TO RE-RUN. Every action is guarded so a second run changes nothing and
# exits 0. The plan tests exactly this.
#
# Usage:  sudo ./setup.sh
#
set -euo pipefail

# --- Configuration ----------------------------------------------------------

readonly APP_USER="aiportfolio"
readonly APP_HOME="/opt/ai-portfolio"
readonly APP_ENV_FILE="/etc/ai-portfolio.env"
readonly PYTHON="python3.12"

readonly PACKAGES=(
  nginx
  certbot
  python3-certbot-nginx
  "${PYTHON}"
  "${PYTHON}-venv"
  "${PYTHON}-dev"
  python3-pip
  ufw
  git
  curl
  ca-certificates
  build-essential
)

# Backup of Oracle's original persisted ruleset, taken once before section 6
# edits it.
readonly IPTABLES_RULES="/etc/iptables/rules.v4"
readonly IPTABLES_BACKUP="/etc/iptables/rules.v4.pre-ai-portfolio"
readonly BLANKET_REJECT="-j REJECT --reject-with icmp-host-prohibited"

# Bound every apt network call. apt's defaults retry for minutes on an
# unreachable mirror, which turns a dead network into what looks like a hang —
# and in CI, into a job that burns its entire timeout before failing.
readonly APT_OPTS=(
  -o Acquire::Retries=2
  -o Acquire::Connect::Timeout=10
  -o Acquire::http::Timeout=20
  -o Acquire::https::Timeout=20
)
readonly APT_UPDATE_ATTEMPTS=3

# --- Output helpers ---------------------------------------------------------

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
ok()   { printf '    \033[0;32mok\033[0m %s\n' "$*"; }
warn() { printf '    \033[0;33m!\033[0m  %s\n' "$*" >&2; }
die()  { printf '\n\033[0;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# --- Preflight --------------------------------------------------------------

[[ ${EUID} -eq 0 ]] || die "must run as root — try: sudo $0"

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  [[ ${ID:-} == "ubuntu" ]] || warn "expected Ubuntu, found '${ID:-unknown}' — continuing anyway"
  [[ ${VERSION_ID:-} == "24.04" ]] || warn "expected Ubuntu 24.04, found '${VERSION_ID:-unknown}'"
else
  warn "/etc/os-release unreadable; cannot verify the distribution"
fi

host_name=$(hostname) || host_name="unknown-host"
machine_arch=$(uname -m) || machine_arch="unknown-arch"
log "Bootstrapping ${host_name} — ${machine_arch}"

# --- 1. System packages -----------------------------------------------------

log "Updating package lists"
export DEBIAN_FRONTEND=noninteractive

# 'apt-get update' exits 0 even when EVERY index fetch fails — the failures are
# only warnings. Reporting success there would mean installing from stale or
# empty lists, so the output is inspected rather than the exit code trusted.
apt_update_output=""
apt_update_ok=false
for attempt in $(seq 1 "${APT_UPDATE_ATTEMPTS}"); do
  if apt_update_output=$(apt-get "${APT_OPTS[@]}" update 2>&1); then
    if grep -qE '^(W: Failed to fetch|E:)' <<<"${apt_update_output}"; then
      warn "attempt ${attempt}/${APT_UPDATE_ATTEMPTS}: some indexes failed to fetch"
    else
      apt_update_ok=true
      break
    fi
  else
    warn "attempt ${attempt}/${APT_UPDATE_ATTEMPTS}: apt-get update failed"
  fi
  if [[ ${attempt} -lt ${APT_UPDATE_ATTEMPTS} ]]; then
    info "retrying in $((attempt * 5))s"
    sleep "$((attempt * 5))"
  fi
done

if [[ ${apt_update_ok} != true ]]; then
  printf '%s\n' "${apt_update_output}" | grep -E '^(W:|E:)' | head -5 >&2
  die "could not refresh package lists after ${APT_UPDATE_ATTEMPTS} attempts.
    Check DNS and outbound HTTP from this VM:
      getent ahostsv4 archive.ubuntu.com
      curl -sI http://ports.ubuntu.com/
    Refusing to continue against stale package lists."
fi
ok "package lists current"

log "Upgrading installed packages"
apt-get "${APT_OPTS[@]}" upgrade -y -qq
ok "system upgraded"

log "Installing packages"
missing=()
for pkg in "${PACKAGES[@]}"; do
  if dpkg-query -W -f='${Status}' "${pkg}" 2>/dev/null | grep -q "^install ok installed$"; then
    info "already present: ${pkg}"
  else
    missing+=("${pkg}")
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  info "installing: ${missing[*]}"
  apt-get "${APT_OPTS[@]}" install -y -qq "${missing[@]}"
  ok "installed ${#missing[@]} package(s)"
else
  ok "all packages already installed"
fi

"${PYTHON}" --version || die "${PYTHON} not available after install"

# --- 2. Service account -----------------------------------------------------
#
# The app never runs as root. A system account with no login shell is enough:
# systemd starts the process, nobody logs in as it.

log "Ensuring service account '${APP_USER}'"
if id -u "${APP_USER}" >/dev/null 2>&1; then
  ok "user '${APP_USER}' already exists"
else
  useradd --system --create-home --home-dir "${APP_HOME}" \
          --shell /usr/sbin/nologin --comment "AI portfolio backend" "${APP_USER}"
  ok "created user '${APP_USER}'"
fi

if [[ ! -d ${APP_HOME} ]]; then
  mkdir -p "${APP_HOME}"
  ok "created ${APP_HOME}"
fi
chown "${APP_USER}:${APP_USER}" "${APP_HOME}"
chmod 750 "${APP_HOME}"
ok "${APP_HOME} owned by ${APP_USER} (750)"

# --- 3. Environment file ----------------------------------------------------
#
# Created empty and root-only. Secrets are written here out-of-band; this
# script must never contain or echo one.

log "Ensuring environment file"
if [[ -f ${APP_ENV_FILE} ]]; then
  ok "${APP_ENV_FILE} already exists (left untouched)"
else
  touch "${APP_ENV_FILE}"
  ok "created empty ${APP_ENV_FILE}"
fi
chown root:"${APP_USER}" "${APP_ENV_FILE}"
chmod 640 "${APP_ENV_FILE}"
ok "${APP_ENV_FILE} root:${APP_USER} (640)"

# --- 4. nginx ---------------------------------------------------------------

log "Ensuring nginx is enabled and running"
systemctl enable --quiet --now nginx
if systemctl is-active --quiet nginx; then
  ok "nginx active"
else
  die "nginx failed to start — check: systemctl status nginx"
fi

# --- 5. Firewall: ufw -------------------------------------------------------
#
# Order matters. SSH is allowed BEFORE enabling, otherwise enabling ufw over an
# SSH session locks you out of the machine permanently.

log "Configuring ufw"
# Port number, not the 'OpenSSH' application profile. That profile is supplied
# by the openssh-server package; naming it makes the firewall step depend on a
# package this script neither installs nor checks for, and it aborts outright
# where the profile is absent.
ufw allow 22/tcp >/dev/null
ok "22/tcp (SSH) allowed"
ufw allow 80/tcp >/dev/null
ok "80/tcp allowed"
ufw allow 443/tcp >/dev/null
ok "443/tcp allowed"

if ufw status | grep -q "^Status: active"; then
  ok "ufw already active"
else
  ufw --force enable >/dev/null
  ok "ufw enabled"
fi

# --- 6. Firewall: Oracle's blanket iptables REJECT --------------------------
#
# Oracle's Ubuntu images ship an iptables ruleset ending in a blanket REJECT on
# INPUT and FORWARD, persisted in /etc/iptables/rules.v4. That rule sits AHEAD
# of every ufw chain, so ports 80/443 stay shut even when the ufw rules and the
# OCI security list both allow them. Verified experimentally: enabling ufw does
# NOT displace it. This is the most common "the port is open but nothing
# connects" trap on OCI.
#
# Note we deliberately do NOT install iptables-persistent: the ufw package
# declares "Breaks: iptables-persistent", so the two cannot coexist on Ubuntu
# 24.04. ufw persists its own rules and is the single source of truth here.
#
# Rules are deleted one at a time rather than by flushing the chain, because
# flushing over SSH can drop the session mid-run.

log "Clearing Oracle's blanket REJECT rules"
if ! command -v iptables >/dev/null 2>&1; then
  warn "iptables not found; skipping (ufw is managing the firewall)"
else
  removed=0
  for chain in INPUT FORWARD; do
    # shellcheck disable=SC2086
    while iptables -C "${chain}" ${BLANKET_REJECT} 2>/dev/null; do
      # shellcheck disable=SC2086
      iptables -D "${chain}" ${BLANKET_REJECT}
      removed=$((removed + 1))
      ok "removed blanket REJECT from ${chain}"
    done
  done
  if [[ ${removed} -eq 0 ]]; then
    info "no blanket REJECT in the running rules"
  fi

  # Strip the persisted copy too. Without this a reboot restores the REJECT and
  # the site silently stops answering — the worst kind of failure, because
  # nothing changed between it working and not.
  if [[ -f ${IPTABLES_RULES} ]]; then
    if grep -qF -- "${BLANKET_REJECT}" "${IPTABLES_RULES}"; then
      if [[ ! -f ${IPTABLES_BACKUP} ]]; then
        cp -a "${IPTABLES_RULES}" "${IPTABLES_BACKUP}"
        ok "backed up original ruleset to ${IPTABLES_BACKUP}"
      fi
      sed -i "\|${BLANKET_REJECT}|d" "${IPTABLES_RULES}"
      ok "stripped blanket REJECT from ${IPTABLES_RULES}"
    else
      info "${IPTABLES_RULES} already free of blanket REJECT"
    fi
  else
    info "${IPTABLES_RULES} absent — nothing persisted to clean"
  fi
fi

# --- 7. Summary -------------------------------------------------------------

log "Done"

python_version=$("${PYTHON}" --version 2>&1) || python_version="unknown"
nginx_version=$(nginx -v 2>&1) || nginx_version="unknown"
certbot_version=$(certbot --version 2>&1) || certbot_version="unknown"
ufw_state=$(ufw status 2>/dev/null | head -1) || ufw_state="unknown"

info "python    : ${python_version}"
info "nginx     : ${nginx_version}"
info "certbot   : ${certbot_version}"
info "app user  : ${APP_USER} (${APP_HOME})"
info "env file  : ${APP_ENV_FILE}"
info "firewall  : ${ufw_state}"
printf '\n    Verify from your own machine:  curl -I http://<vm-public-ip>\n\n'
