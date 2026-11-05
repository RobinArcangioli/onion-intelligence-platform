#!/usr/bin/env bash
# Install reviewed systemd definitions, but NEVER enable timers or network alerts.
set -Eeuo pipefail
[[ "$EUID" == 0 ]] || { echo 'Run with sudo/root' >&2; exit 1; }
ROOT=/opt/oip/onion-intelligence-platform
[[ -f "$ROOT/deploy/ovh/deploy.sh" && -f "$ROOT/deploy/ovh/monitor.py" ]] || {
  echo "OIP deployment missing under $ROOT" >&2; exit 1;
}
install -d -m 0700 -o root -g root /etc/oip /var/lib/oip-monitor
for unit in oip-monitor.service oip-monitor.timer oip-backup.service oip-backup.timer oip-alert@.service; do
  install -m 0644 -o root -g root "$ROOT/deploy/ovh/systemd/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/oip-{monitor,backup}.{service,timer} /etc/systemd/system/oip-alert@.service
echo 'PASS: systemd units installed, timers NOT enabled; follow M1-RUNBOOK.md'
