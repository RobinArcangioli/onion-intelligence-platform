#!/usr/bin/env bash
# Non-destructive restore rehearsal: create and drop a disposable PostgreSQL DB.
# Does NOT call the destructive production restore-db.sh script.
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo 'Docker is required' >&2; exit 2; }

workdir="$(mktemp -d "${TMPDIR:-/tmp}/oip-restore-check.XXXXXXXX")"
verification_db="oip_restore_check_${$}_${RANDOM}"
created=false
cleanup() {
  if [[ "$created" == true ]]; then
    docker compose exec -T db sh -ec 'exec dropdb -U "$POSTGRES_USER" --if-exists "$1"' sh "$verification_db" >/dev/null 2>&1 || \
      echo "WARNING: remove temporary database $verification_db manually" >&2
  fi
  rm -f -- "$workdir/snapshot.dump"
  rmdir -- "$workdir" 2>/dev/null || true
}
trap cleanup EXIT

printf 'Creating disposable backup snapshot...\n'
# Secrets remain inside container's environment, never in command arguments.
docker compose exec -T db sh -ec 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' > "$workdir/snapshot.dump"
[[ -s "$workdir/snapshot.dump" ]] || { echo 'FAIL: empty backup' >&2; exit 1; }
[[ "$(head -c 5 "$workdir/snapshot.dump")" == 'PGDMP' ]] || { echo 'FAIL: invalid pg_dump header' >&2; exit 1; }

docker compose exec -T db sh -ec 'exec createdb -U "$POSTGRES_USER" "$1"' sh "$verification_db"
created=true
printf 'Restoring into disposable database (never production)...\n'
docker compose exec -T db sh -ec \
  'exec pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --no-acl --single-transaction --exit-on-error' \
  sh "$verification_db" < "$workdir/snapshot.dump"

# Sanity check for a migrated OIP schema. Output is minimal and non-sensitive.
check="$(docker compose exec -T db sh -ec \
  'exec psql -U "$POSTGRES_USER" -d "$1" -Atqc "SELECT CASE WHEN to_regclass('\''public.onion_sources'\'') IS NOT NULL AND to_regclass('\''public.alembic_version'\'') IS NOT NULL THEN '\''OK'\'' ELSE '\''FAIL'\'' END"' \
  sh "$verification_db" | tr -d '\r')"
[[ "$check" == 'OK' ]] || { echo 'FAIL: required OIP tables missing after restore' >&2; exit 1; }
printf 'PASS: pg_dump, temporary pg_restore and required schema checks\n'
