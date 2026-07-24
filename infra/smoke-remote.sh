#!/usr/bin/env bash
#
# Post-deploy smoke test against the live VM.
#
# /health is always checked and is safe — it touches nothing downstream. /chat
# and /contact are opt-in behind --all because they cost real money (a Claude
# call) and send real email (a contact notification to LJ). A routine redeploy
# should not do either; a first deploy or a "prove the whole chain" check
# should.
#
# Usage:
#   ./smoke-remote.sh http://<vm-ip>           # /health only
#   ./smoke-remote.sh --all http://<vm-ip>     # + /chat and /contact
#
set -euo pipefail

WITH_LIVE=false
if [[ ${1:-} == "--all" ]]; then
  WITH_LIVE=true
  shift
fi

URL="${1:-}"
[[ -n ${URL} ]] || { printf 'usage: %s [--all] <base-url>\n' "$0" >&2; exit 2; }
URL="${URL%/}"

pass() { printf '\033[0;32mPASS\033[0m %s\n' "$*"; }
fail() { printf '\033[0;31mFAIL\033[0m %s\n' "$*" >&2; }

failures=0
check() { "$@" || failures=$((failures + 1)); }

# --- /health ----------------------------------------------------------------

check_health() {
  local body
  body=$(curl -fsS --max-time 10 "${URL}/health") || { fail "/health did not return 200"; return 1; }
  if [[ ${body} == '{"status":"ok"}' ]]; then
    pass "/health -> ${body}"
  else
    fail "/health returned unexpected body: ${body}"
    return 1
  fi
}

# --- /chat (real Claude call) -----------------------------------------------

check_chat() {
  local response status
  response=$(curl -fsS --max-time 60 -X POST "${URL}/chat" \
    -H 'Content-Type: application/json' \
    -d '{"question":"Who does Ljuben currently work for?"}') \
    || { fail "/chat did not return 200"; return 1; }

  # Grounded answer, so it must mention the current employer. jq if present, a
  # plain substring check otherwise — this script must run on a bare machine.
  if command -v jq >/dev/null 2>&1; then
    status=$(jq -r 'if .answer and (.sources | length >= 0) then "ok" else "bad" end' <<<"${response}" 2>/dev/null) || status="bad"
    [[ ${status} == "ok" ]] || { fail "/chat response missing answer/sources: ${response}"; return 1; }
  fi
  if grep -qi "AI Talent" <<<"${response}"; then
    pass "/chat answered and named the current employer"
  else
    fail "/chat answer did not mention the expected employer: ${response}"
    return 1
  fi
}

# --- /contact (real email) --------------------------------------------------

check_contact() {
  # ASCII-only payload on purpose. This script is run from Git Bash on Windows,
  # which mangles multi-byte UTF-8 characters (e.g. an em-dash) in a curl -d
  # argument and produces a 400 — even though the server handles UTF-8 correctly
  # (the real client is the browser's fetch, which sends proper UTF-8). Keep the
  # smoke payload plain ASCII so the test says something about the server, not
  # about the shell it ran from.
  local response
  response=$(curl -fsS --max-time 60 -X POST "${URL}/contact" \
    -H 'Content-Type: application/json' \
    -d '{"name":"Smoke Test","email":"smoke-test@example.com","message":"Automated post-deploy smoke test - please ignore. If you received this email, the contact chain works end to end on the VM."}') \
    || { fail "/contact did not return 200"; return 1; }

  if grep -q '"received":true' <<<"${response}"; then
    pass "/contact accepted the submission (check LJ's inbox for the notification)"
  else
    fail "/contact did not acknowledge: ${response}"
    return 1
  fi
}

# --- Run --------------------------------------------------------------------

printf '\n\033[1;34m==>\033[0m Smoke test against %s\n' "${URL}"
check check_health

if [[ ${WITH_LIVE} == true ]]; then
  printf '    \033[0;33m--all\033[0m: the next two checks spend money and send email\n'
  check check_chat
  check check_contact
else
  printf '    (skipping /chat and /contact — pass --all to include them)\n'
fi

printf '\n'
if [[ ${failures} -eq 0 ]]; then
  pass "all checks passed"
else
  fail "${failures} check(s) failed"
  exit 1
fi
