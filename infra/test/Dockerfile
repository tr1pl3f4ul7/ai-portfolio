# Test harness for infra/setup.sh.
#
# Ubuntu 24.04 aarch64 with systemd as PID 1 — matching the Oracle Ampere A1
# target. systemd matters: setup.sh manages units and ufw, and a stock container
# has no init, so systemctl would fail and the script would abort at section 4
# without testing anything below it.
#
# Nothing setup.sh installs is pre-installed here; the run exercises the real
# package path.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV container=docker

RUN apt-get update -qq \
 && apt-get install -y -qq systemd systemd-sysv dbus iproute2 iptables \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Units that are meaningless in a container and only produce noise.
RUN find /etc/systemd/system /lib/systemd/system \
      -path '*.wants/*' \
      \( -name '*udev*' -o -name '*getty*' -o -name '*remote-fs*' \) \
      -exec rm -f {} + || true

STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
