#!/usr/bin/env bash
# Reproduces the firewall state an Oracle Ubuntu image arrives in: the real
# default ruleset loaded into the running chains AND persisted to
# /etc/iptables/rules.v4.
#
# This is Oracle's actual ruleset, copied from a live Ampere A1 instance, not an
# approximation. Two details matter and were both learned the hard way:
#
#  1. It accepts RELATED,ESTABLISHED *before* the blanket REJECT. Seeding only
#     the REJECT also rejects DNS replies and breaks the container's network,
#     which a real VM does not do.
#  2. It defines an InstanceServices chain governing the link-local range
#     (metadata, iSCSI, DNS, NTP). setup.sh must preserve it while removing the
#     blanket REJECT, so the test needs it present to prove that.
set -euo pipefail

mkdir -p /etc/iptables
cat > /etc/iptables/rules.v4 <<'EOF'
# CLOUD_IMG: This file was created/modified by the Cloud Image build process
# iptables configuration for Oracle Cloud Infrastructure

# See the Oracle-Provided Images section in the Oracle Cloud Infrastructure
# documentation for security impact of modifying or removing these rule

*filter
:INPUT ACCEPT [0:0]
:FORWARD ACCEPT [0:0]
:OUTPUT ACCEPT [0:0]
:InstanceServices - [0:0]
-A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT
-A INPUT -p icmp -j ACCEPT
-A INPUT -i lo -j ACCEPT
-A INPUT -p tcp -m state --state NEW -m tcp --dport 22 -j ACCEPT
-A INPUT -j REJECT --reject-with icmp-host-prohibited
-A FORWARD -j REJECT --reject-with icmp-host-prohibited
-A OUTPUT -d 169.254.0.0/16 -j InstanceServices
-A InstanceServices -d 169.254.0.2/32 -p tcp -m owner --uid-owner 0 -m tcp --dport 3260 -j ACCEPT
-A InstanceServices -d 169.254.2.0/24 -p tcp -m owner --uid-owner 0 -m tcp --dport 3260 -j ACCEPT
-A InstanceServices -d 169.254.4.0/24 -p tcp -m owner --uid-owner 0 -m tcp --dport 3260 -j ACCEPT
-A InstanceServices -d 169.254.5.0/24 -p tcp -m owner --uid-owner 0 -m tcp --dport 3260 -j ACCEPT
-A InstanceServices -d 169.254.0.2/32 -p tcp -m tcp --dport 80 -j ACCEPT
-A InstanceServices -d 169.254.169.254/32 -p udp -m udp --dport 53 -j ACCEPT
-A InstanceServices -d 169.254.169.254/32 -p tcp -m tcp --dport 53 -j ACCEPT
-A InstanceServices -d 169.254.0.3/32 -p tcp -m owner --uid-owner 0 -m tcp --dport 80 -j ACCEPT
-A InstanceServices -d 169.254.0.4/32 -p tcp -m tcp --dport 80 -j ACCEPT
-A InstanceServices -d 169.254.169.254/32 -p tcp -m tcp --dport 80 -j ACCEPT
-A InstanceServices -d 169.254.169.254/32 -p udp -m udp --dport 67 -j ACCEPT
-A InstanceServices -d 169.254.169.254/32 -p udp -m udp --dport 69 -j ACCEPT
-A InstanceServices -d 169.254.169.254/32 -p udp --dport 123 -j ACCEPT
-A InstanceServices -d 169.254.0.0/16 -p tcp -m tcp -j REJECT --reject-with tcp-reset
-A InstanceServices -d 169.254.0.0/16 -p udp -m udp -j REJECT --reject-with icmp-port-unreachable
COMMIT
EOF

iptables-restore < /etc/iptables/rules.v4

echo "seeded Oracle-style firewall state"
echo "--- running INPUT ---"
iptables -S INPUT
echo "blanket REJECT lines persisted: $(grep -c -- '-j REJECT --reject-with icmp-host-prohibited' /etc/iptables/rules.v4)"
echo "InstanceServices rules running: $(iptables-save | grep -c 'InstanceServices')"

# Sanity: outbound DNS must still work, exactly as it does on a real VM.
if getent ahostsv4 archive.ubuntu.com >/dev/null 2>&1; then
  echo "DNS after seeding: OK"
else
  echo "DNS after seeding: BROKEN — the seed is wrong, not the script under test" >&2
  exit 1
fi
