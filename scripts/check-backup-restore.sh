#!/usr/bin/env bash
# Non-destructive restore rehearsal: create and drop a disposable PostgreSQL DB.
# Does NOT call the destructive production restore-db.sh script.
set -Eeuo pipefail
umask 077
unset DOCKER_HOST DOCKER_CONTEXT
command -v docker >/dev/null || { echo 'Docker is required' >&2; exit 2; }

[[ $# == 1 && -f "$1" && ! -L "$1" ]] || {
  echo 'Usage: scripts/check-backup-restore.sh LOCAL_PRE_MIGRATION_DUMP' >&2
  exit 2
}
archive="$(realpath -- "$1")"
cd "$(dirname "$0")/.."
[[ "$(head -c 5 "$archive")" == 'PGDMP' ]] || { echo 'FAIL: invalid pg_dump header' >&2; exit 1; }
verification_db="oip_restore_check_${$}_${RANDOM}"
created=false
cleanup() {
  if [[ "$created" == true ]]; then
    docker --host unix:///var/run/docker.sock compose exec -T db sh -ec 'exec dropdb -U "$POSTGRES_USER" --if-exists "$1"' sh "$verification_db" >/dev/null 2>&1 || \
      echo "WARNING: remove temporary database $verification_db manually" >&2
  fi
}
trap cleanup EXIT

docker --host unix:///var/run/docker.sock compose exec -T db sh -ec 'exec createdb -U "$POSTGRES_USER" "$1"' sh "$verification_db"
created=true
printf 'Restoring into disposable database (never production)...\n'
docker --host unix:///var/run/docker.sock compose exec -T db sh -ec \
  'exec pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --no-acl --single-transaction --exit-on-error' \
  sh "$verification_db" < "$archive"

# Sanity check for a migrated OIP schema. Output is minimal and non-sensitive.
check="$(docker --host unix:///var/run/docker.sock compose exec -T db sh -ec \
  'exec psql -U "$POSTGRES_USER" -d "$1" -Atqc "SELECT CASE WHEN to_regclass('\''public.onion_sources'\'') IS NOT NULL AND to_regclass('\''public.alembic_version'\'') IS NOT NULL THEN '\''OK'\'' ELSE '\''FAIL'\'' END"' \
  sh "$verification_db" | tr -d '\r')"
[[ "$check" == 'OK' ]] || { echo 'FAIL: required OIP tables missing after restore' >&2; exit 1; }
printf 'PASS: local archive restored into temporary database; required schema found\n'
