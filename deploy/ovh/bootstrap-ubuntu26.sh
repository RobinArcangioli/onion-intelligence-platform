#!/usr/bin/env bash
# Fresh OVH VPS-1 Ubuntu 26.04 LTS: install prerequisites and official Docker Engine.
# Deliberately does NOT modify SSH, firewall, Docker containers, or application data.
set -Eeuo pipefail
umask 077

die() { printf 'NO-GO: %s\n' "$*" >&2; exit 1; }
[[ "$(id -u)" -eq 0 ]] || die 'Run as root: sudo bash deploy/ovh/bootstrap-ubuntu26.sh'
[[ -f /etc/os-release ]] || die 'Cannot identify OS'
# shellcheck disable=SC1091
. /etc/os-release
[[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 26.04 && "${VERSION_CODENAME:-}" == resolute ]] ||
  die 'Only Ubuntu 26.04 LTS (resolute) is supported by this bootstrap'
case "$(dpkg --print-architecture)" in amd64|arm64) ;; *) die 'Requires Ubuntu amd64 or arm64' ;; esac
command -v apt-get >/dev/null || die 'apt-get not found'
for name in docker.io docker-compose docker-compose-v2 podman-docker; do
  if dpkg-query -W -f='${db:Status-Abbrev}' "$name" 2>/dev/null | grep -q '^ii'; then
    die "Conflicting package installed: $name; review Docker migration before proceeding"
  fi
done

printf 'Preparing Ubuntu 26.04; SSH settings and firewall will NOT be changed.\n'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl python3 unzip git age openssh-client gnupg

# Follow the official Docker CE apt repository procedure (not get.docker.com).
install -d -m 0755 /etc/apt/keyrings
keytmp="$(mktemp)"
trap 'rm -f "$keytmp"' EXIT
curl -fsSL --retry 3 https://download.docker.com/linux/ubuntu/gpg -o "$keytmp"
# Docker's documented apt signing-key fingerprint.
expected='9DC858229FC7DD38854AE2D88D81803C0EBFCD88'
found="$(gpg --show-keys --with-colons "$keytmp" 2>/dev/null | awk -F: '$1 == "fpr" {print $10; exit}')"
[[ "$found" == "$expected" ]] || die 'Unexpected Docker apt signing key fingerprint'
install -m 0644 "$keytmp" /etc/apt/keyrings/docker.asc
cat >/etc/apt/sources.list.d/docker.sources <<'SOURCES'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: resolute
Components: stable
Architectures: amd64 arm64
Signed-By: /etc/apt/keyrings/docker.asc
SOURCES
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

docker version --format '{{.Server.Version}}' >/dev/null || die 'Docker daemon unavailable'
docker compose version || die 'Docker Compose v2 unavailable'
install -d -o root -g root -m 0700 /opt/oip
printf 'PASS: Docker Engine and Compose installed; /opt/oip prepared.\n'
printf 'NEXT: manually verify SSH key access and firewall, then generate fresh OIP secrets.\n'
