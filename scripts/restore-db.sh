#!/usr/bin/env bash
# Destructive restore. Requires API/gateway/collector to be stopped.
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")/.."
if [[ $# -ne 2 || "$2" != '--confirm-restore' ]]; then
  echo 'Usage: scripts/restore-db.sh backups/file.dump --confirm-restore' >&2
  exit 2
fi
file="$1"
if [[ ! -f "$file" || ! -s "$file" ]]; then echo 'Backup not found/empty' >&2; exit 1; fi
# Safety: no active application components writing during restore.
if [[ -n "$(docker compose ps --status running -q api gateway collector)" ]]; then
  echo 'Stop API, gateway and collector before restoring (docker compose stop api gateway)' >&2
  exit 1
fi
docker compose exec -T db sh -ec 'exec pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-acl --single-transaction --exit-on-error' < "$file"
echo 'Restore completed. Restart API/gateway and verify migrations.'
