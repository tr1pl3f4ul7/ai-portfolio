#!/usr/bin/env bash
# Captures every piece of state setup.sh owns, so two snapshots can be diffed
# to prove idempotency. Run as root inside the test container.
set -uo pipefail

echo "== user =="
id -u aiportfolio
id -gn aiportfolio
echo "passwd_entries=$(grep -c '^aiportfolio:' /etc/passwd)"
echo "group_entries=$(grep -c '^aiportfolio:' /etc/group)"

echo "== paths =="
stat -c '%U:%G %a %n' /opt/ai-portfolio
stat -c '%U:%G %a %n' /etc/ai-portfolio.env
echo "env_file_bytes=$(wc -c < /etc/ai-portfolio.env)"

echo "== nginx =="
echo "enabled=$(systemctl is-enabled nginx 2>&1)"
echo "active=$(systemctl is-active nginx 2>&1)"

echo "== ufw =="
ufw status | sed 's/[[:space:]]*$//'
echo "ufw_allow_count=$(ufw status | grep -c ALLOW)"

echo "== iptables INPUT =="
iptables -S INPUT
echo "== iptables FORWARD =="
iptables -S FORWARD
echo "blanket_reject_running=$(iptables -S | grep -c -- '-j REJECT --reject-with icmp-host-prohibited')"

echo "== persisted rules =="
echo "rules_v4_exists=$(test -f /etc/iptables/rules.v4 && echo yes || echo no)"
echo "blanket_reject_persisted=$(grep -c -- '-j REJECT --reject-with icmp-host-prohibited' /etc/iptables/rules.v4 2>/dev/null || echo 0)"
echo "backup_exists=$(test -f /etc/iptables/rules.v4.pre-ai-portfolio && echo yes || echo no)"
echo "backup_reject_lines=$(grep -c -- '-j REJECT --reject-with icmp-host-prohibited' /etc/iptables/rules.v4.pre-ai-portfolio 2>/dev/null || echo 0)"

echo "== functional: HTTP on port 80 =="
echo "curl_status=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1/ || echo FAILED)"
