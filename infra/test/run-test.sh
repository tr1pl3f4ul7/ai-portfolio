#!/usr/bin/env bash
#
# Idempotency test for infra/setup.sh, required by Step 1.2 of the build plan.
#
# Boots an Ubuntu 24.04 container with systemd as PID 1, seeds it with the
# firewall state an Oracle image arrives in, then runs setup.sh TWICE and
# asserts the resulting state is byte-identical. Also asserts nginx actually
# answers on port 80 through the firewall, rather than merely looking
# configured.
#
# Usage:  ./run-test.sh
# Requires: docker
#
# Runs on Linux, macOS, and Windows/Git Bash — path translation is handled
# below.
#
set -euo pipefail

readonly IMAGE="ai-portfolio-setup-test:24.04"
readonly CONTAINER="ai-portfolio-setup-test"
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
readonly HERE
readonly SETUP="${HERE}/../setup.sh"

# Git Bash rewrites Unix-looking paths into Windows paths before handing them to
# a native binary, which mangles every container-side path (/root/setup.sh
# becomes C:/Program Files/Git/root/setup.sh). Suppress it globally and convert
# host paths explicitly with cygpath instead. No-ops on Linux and macOS.
if command -v cygpath >/dev/null 2>&1; then
  hostpath() { cygpath -w "$1"; }
  export MSYS_NO_PATHCONV=1
else
  hostpath() { printf '%s' "$1"; }
fi

pass() { printf '\033[0;32mPASS\033[0m %s\n' "$*"; }
fail() { printf '\033[0;31mFAIL\033[0m %s\n' "$*" >&2; }
step() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

[[ -f ${SETUP} ]] || { fail "setup.sh not found at ${SETUP}"; exit 1; }

cleanup() { docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true; }
trap cleanup EXIT

step "Building test image"
docker build -q -t "${IMAGE}" "$(hostpath "${HERE}")" >/dev/null

step "Starting container (systemd as PID 1)"
cleanup
docker run -d --name "${CONTAINER}" \
  --privileged --cgroupns=host \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  "${IMAGE}" >/dev/null

for _ in $(seq 1 20); do
  state=$(docker exec "${CONTAINER}" systemctl is-system-running 2>&1 || true)
  case "${state}" in running | degraded) break ;; esac
  sleep 3
done
[[ ${state} == running || ${state} == degraded ]] || { fail "systemd did not start (${state})"; exit 1; }
pass "systemd is ${state}"

step "Copying scripts in"
docker cp "$(hostpath "${SETUP}")" "${CONTAINER}:/root/setup.sh"
docker cp "$(hostpath "${HERE}/seed-oracle.sh")" "${CONTAINER}:/root/seed-oracle.sh"
docker cp "$(hostpath "${HERE}/snapshot.sh")" "${CONTAINER}:/root/snapshot.sh"
docker exec "${CONTAINER}" chmod +x /root/setup.sh /root/seed-oracle.sh /root/snapshot.sh

step "Seeding Oracle-style firewall state"
docker exec "${CONTAINER}" /root/seed-oracle.sh

failures=0

step "Run 1"
if docker exec "${CONTAINER}" bash -c '/root/setup.sh > /root/run1.log 2>&1'; then
  pass "run 1 exited 0"
else
  fail "run 1 failed — last 30 lines follow"
  docker exec "${CONTAINER}" tail -30 /root/run1.log 2>/dev/null || true
  exit 1
fi
docker exec "${CONTAINER}" bash -c '/root/snapshot.sh > /root/state1.txt 2>&1'

step "Run 2 (idempotency)"
if docker exec "${CONTAINER}" bash -c '/root/setup.sh > /root/run2.log 2>&1'; then
  pass "run 2 exited 0"
else
  fail "run 2 failed — the script is not safe to re-run"
  docker exec "${CONTAINER}" tail -30 /root/run2.log 2>/dev/null || true
  failures=$((failures + 1))
fi
docker exec "${CONTAINER}" bash -c '/root/snapshot.sh > /root/state2.txt 2>&1'

step "Comparing state"
if docker exec "${CONTAINER}" diff -u /root/state1.txt /root/state2.txt; then
  pass "state identical after second run — no drift, no duplicates"
else
  fail "state drifted between runs"
  failures=$((failures + 1))
fi

step "Asserting outcomes"
check() {
  local label=$1 expected=$2 actual
  actual=$(docker exec "${CONTAINER}" bash -c "grep -m1 '^${label}=' /root/state2.txt | cut -d= -f2-" 2>/dev/null | tr -d '\r')
  if [[ ${actual} == "${expected}" ]]; then
    pass "${label}=${actual}"
  else
    fail "${label}: expected '${expected}', got '${actual}'"
    failures=$((failures + 1))
  fi
}

check passwd_entries 1              # user created exactly once
check group_entries 1
check ufw_allow_count 6             # 22/80/443 over v4 and v6
check blanket_reject_running 0      # Oracle's REJECT gone from live chains
check blanket_reject_persisted 0    # ...and from rules.v4, so it survives reboot
check backup_exists yes             # original ruleset recoverable
check curl_status 200               # nginx actually serves through the firewall
check nginx_logrotate_exists yes    # ships with the nginx package
check journald_dropin_exists yes    # Step 8.2's journald cap was written

# Oracle's link-local egress rules must survive, not be collateral damage --
# and must be hooked where they actually see traffic. Appended to OUTPUT the
# jump lands after ufw's chains, receives zero packets, and is inert; it has to
# be inside ufw-before-output. Measured with packet counters on the VM; a
# container has no route to 169.254.0.0/16, so only the structure is checked
# here.
check instanceservices_hooked_early 1

instsvc=$(docker exec "${CONTAINER}" bash -c "grep -m1 '^instanceservices_in_ufw=' /root/state2.txt | cut -d= -f2-" | tr -d '\r')
if [[ ${instsvc} -gt 0 ]]; then
  pass "instanceservices_in_ufw=${instsvc} (ported into before.rules)"
else
  fail "InstanceServices rules were not ported into ufw's before.rules"
  failures=$((failures + 1))
fi

# Simulate a reboot properly. netfilter-persistent is gone, so rules.v4 is NOT
# re-applied — ufw alone rebuilds the firewall from before.rules. Flushing and
# restarting ufw reproduces that.
step "Simulating reboot (flush tables, let ufw rebuild)"
docker exec "${CONTAINER}" bash -c 'iptables -F; iptables -X 2>/dev/null; systemctl restart ufw' >/dev/null 2>&1

reject_after=$(docker exec "${CONTAINER}" bash -c "iptables -S | grep -c -- '-j REJECT --reject-with icmp-host-prohibited' || true" | tr -d '\r')
if [[ ${reject_after} == "0" ]]; then
  pass "blanket REJECT does not return after reboot"
else
  fail "blanket REJECT returned after reboot (${reject_after} rules) — port 80 would silently close"
  failures=$((failures + 1))
fi

instsvc_after=$(docker exec "${CONTAINER}" bash -c "iptables-save | grep -c 'InstanceServices' || true" | tr -d '\r')
if [[ ${instsvc_after} -gt 0 ]]; then
  pass "InstanceServices restored after reboot (${instsvc_after} rules)"
else
  fail "InstanceServices missing after reboot — Oracle's egress hardening lost"
  failures=$((failures + 1))
fi

# After a reboot nothing re-applies rules.v4, so the ONLY jump should be the one
# ufw restores into ufw-before-output. A jump left in plain OUTPUT would mean
# the rules are present but never reached.
hooked_after=$(docker exec "${CONTAINER}" bash -c "iptables -S ufw-before-output | grep -c 'InstanceServices' || true" | tr -d '\r')
plain_after=$(docker exec "${CONTAINER}" bash -c "iptables -S OUTPUT | grep -c 'InstanceServices' || true" | tr -d '\r')
if [[ ${hooked_after} -ge 1 && ${plain_after} == "0" ]]; then
  pass "after reboot the jump is in ufw-before-output only (not inert in OUTPUT)"
else
  fail "after reboot: ufw-before-output=${hooked_after}, OUTPUT=${plain_after} — expected >=1 and 0"
  failures=$((failures + 1))
fi

http_after=$(docker exec "${CONTAINER}" bash -c "curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1/ || echo FAILED" | tr -d '\r')
if [[ ${http_after} == "200" ]]; then
  pass "nginx still answers 200 after reboot"
else
  fail "nginx returned '${http_after}' after reboot"
  failures=$((failures + 1))
fi

echo
if [[ ${failures} -eq 0 ]]; then
  printf '\033[0;32mALL CHECKS PASSED\033[0m\n'
  exit 0
fi
printf '\033[0;31m%d CHECK(S) FAILED\033[0m\n' "${failures}"
exit 1
