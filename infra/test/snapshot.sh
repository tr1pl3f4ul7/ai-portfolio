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

echo "== InstanceServices (Oracle link-local egress rules) =="
echo "instanceservices_running=$(iptables-save 2>/dev/null | grep -c 'InstanceServices' || echo 0)"
echo "instanceservices_in_ufw=$(grep -c 'InstanceServices' /etc/ufw/before.rules 2>/dev/null || echo 0)"
# Presence is not enough. The jump must sit in ufw-before-output; appended to
# OUTPUT it lands after ufw's chains, receives zero packets, and does nothing.
echo "instanceservices_hooked_early=$(iptables -S ufw-before-output 2>/dev/null | grep -c 'InstanceServices' || echo 0)"
echo "instanceservices_in_plain_output=$(iptables -S OUTPUT 2>/dev/null | grep -c 'InstanceServices' || echo 0)"

echo "== persisted rules =="
echo "rules_v4_exists=$(test -f /etc/iptables/rules.v4 && echo yes || echo no)"
echo "blanket_reject_persisted=$(grep -c -- '-j REJECT --reject-with icmp-host-prohibited' /etc/iptables/rules.v4 2>/dev/null || echo 0)"
echo "backup_exists=$(test -f /etc/iptables/rules.v4.pre-ai-portfolio && echo yes || echo no)"
echo "backup_reject_lines=$(grep -c -- '-j REJECT --reject-with icmp-host-prohibited' /etc/iptables/rules.v4.pre-ai-portfolio 2>/dev/null || echo 0)"

echo "== functional: HTTP on port 80 =="
echo "curl_status=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1/ || echo FAILED)"

echo "== log retention (Step 8.2) =="
echo "nginx_logrotate_exists=$(test -f /etc/logrotate.d/nginx && echo yes || echo no)"
echo "journald_dropin_exists=$(test -f /etc/systemd/journald.conf.d/ai-portfolio.conf && echo yes || echo no)"
echo "journald_dropin_sha=$(sha256sum /etc/systemd/journald.conf.d/ai-portfolio.conf 2>/dev/null | cut -d' ' -f1)"
