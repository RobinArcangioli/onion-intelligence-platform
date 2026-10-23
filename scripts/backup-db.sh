#!/usr/bin/env bash
# Encrypted/offline storage recommended. Dumps contain sensitive project metadata.
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")/.."
out="${1:-backups/oip-$(date -u +%Y%m%dT%H%M%SZ).dump}"
if [[ -e "$out" ]]; then echo 'Backup destination already exists' >&2; exit 1; fi
mkdir -p "$(dirname "$out")"
tmp="$(mktemp "${out}.tmp.XXXXXXXX")"
trap 'rm -f -- "$tmp"' EXIT
# Write to host, not the database container. Never print credentials.
docker compose exec -T db sh -ec 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' > "$tmp"
if [[ ! -s "$tmp" ]]; then echo 'Empty backup refused' >&2; exit 1; fi
mv -- "$tmp" "$out"
trap - EXIT
printf 'Backup created: %s (mode 0600)\n' "$out"
