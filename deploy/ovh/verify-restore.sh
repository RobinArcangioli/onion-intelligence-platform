#!/usr/bin/env bash
# On an ISOLATED recovery PC with Docker + age. NEVER run on the production VPS.
# Usage: ./verify-restore.sh path/to/backup.dump.age path/to/recovery-key.txt
set -Eeuo pipefail
umask 077
[[ $# -eq 2 ]] || { echo 'Usage: verify-restore.sh ARCHIVE.dump.age AGE_PRIVATE_KEY' >&2; exit 2; }
archive="$1"; key="$2"
[[ -f "$archive" && ! -L "$archive" && -f "$key" && ! -L "$key" ]] || exit 2
for bin in age docker; do command -v "$bin" >/dev/null || { echo "Missing $bin" >&2; exit 2; }; done
container="oip-restore-test-$PPID-$$"
cleanup() { docker rm -f "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT
# No network, no host port, no persistent named volume, disposable container.
docker run -d --rm --name "$container" --network none \
  -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17-alpine >/dev/null
ready=0
for _ in $(seq 1 60); do
  if docker exec "$container" pg_isready -U postgres -d postgres >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 1
done
[[ "$ready" == 1 ]] || { echo 'NO-GO: recovery database not ready' >&2; exit 1; }
# A valid archive listing alone is insufficient. Restore all data and indexes.
age -d -i "$key" "$archive" | docker exec -i "$container" \
  pg_restore -U postgres -d postgres --no-owner --no-acl --exit-on-error --single-transaction
# Query the restored schema, not the source database.
version="$(docker exec "$container" psql -U postgres -d postgres -AtXq \
  -c 'SELECT version_num FROM alembic_version LIMIT 1')"
[[ "$version" == 0008_manual_queue ]] || {
  echo "NO-GO: restored database schema version differs from expected RC2" >&2; exit 1;
}
tables="$(docker exec "$container" psql -U postgres -d postgres -AtXq \
  -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
[[ "$tables" =~ ^[1-9][0-9]*$ ]] || { echo 'NO-GO: restored schema empty' >&2; exit 1; }
printf 'PASS: isolated full restore completed, expected schema found, public tables=%s\n' "$tables"
