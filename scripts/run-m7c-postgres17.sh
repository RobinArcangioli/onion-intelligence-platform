#!/usr/bin/env bash
# M7-C1 isolated PostgreSQL 17 rehearsal. NEVER run from /opt/oip or on production.
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Run M7-C1 on a NON-PRODUCTION developer/CI host with Docker and PostgreSQL 17.
Requires OIP_CONFIRM_DISPOSABLE_PG17=yes. Creates ONE disposable container, with
RAM-backed PostgreSQL data and port bound to 127.0.0.1:15432; removes it on exit.
Never run on vps-ovh or against any OIP production database.
EOF
}
if [[ "${1:-}" == '--help' ]]; then usage; exit 0; fi
if [[ "${1:-}" != '' ]]; then echo 'Unknown option' >&2; exit 2; fi
if [[ "${OIP_CONFIRM_DISPOSABLE_PG17:-}" != 'yes' ]]; then
  echo 'REFUSED: explicitly set OIP_CONFIRM_DISPOSABLE_PG17=yes on a disposable test host' >&2
  exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "${root}" == /opt/oip/* || "${root}" == /opt/oip || "$(hostname -s)" == vps-ovh \
      || -d /opt/oip/onion-intelligence-platform ]]; then
  echo 'REFUSED: OIP production paths/hosts must not run the destructive test suite' >&2
  exit 2
fi
if [[ -n "${DOCKER_HOST:-}" || -n "${DOCKER_CONTEXT:-}" ]]; then
  echo 'REFUSED: Docker environment overrides are not allowed for this local rehearsal' >&2
  exit 2
fi
if [[ -n "${OIP_M7C_TEST_DSN:-}" || -n "${OIP_DATABASE_URL:-}" ]]; then
  echo 'REFUSED: database environment variables present. Unset them for this isolated rehearsal.' >&2
  exit 2
fi
for executable in docker python3; do
  if ! command -v "$executable" >/dev/null 2>&1; then
    echo "MISSING: $executable is needed; nothing was started" >&2
    exit 2
  fi
done
# Enforce a local Unix-socket daemon; a saved remote Docker context can be
# active even when DOCKER_HOST is unset.
daemon_host="$(docker context inspect "$(docker context show)" \
  --format '{{ (index .Endpoints "docker").Host }}' 2>/dev/null || true)"
if [[ "$daemon_host" != unix://* ]]; then
  echo 'REFUSED: local Docker Unix-socket context required (no remote daemon)' >&2
  exit 2
fi
if ! docker info >/dev/null 2>&1; then
  echo 'Docker is unavailable; nothing was started' >&2
  exit 2
fi
if ! python3 -c 'import psycopg, pytest, sqlalchemy, alembic' >/dev/null 2>&1; then
  echo 'Python test dependencies missing: install the backend dev dependencies on this test host' >&2
  exit 2
fi

# No local .env is read. This is a random disposable database credential.
password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
name="oip-m7c-only-$(python3 -c 'import secrets; print(secrets.token_hex(5))')"
cid=''
cleanup() {
  local code=$?
  trap - EXIT INT TERM
  if [[ -n "$cid" ]]; then
    docker stop "$cid" >/dev/null 2>&1 || true
  fi
  exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# No host database/volume is mounted. The database lives only in the tmpfs.
# Its published port is LOOPBACK ONLY, and not the PostgreSQL production port.
cid="$(docker run --detach --rm --name "$name" \
  --publish '127.0.0.1:15432:5432' \
  --user 70:70 \
  --tmpfs '/var/lib/postgresql/data:rw,size=768m,uid=70,gid=70,mode=0700' \
  --memory 1024m --cpus 1 --pids-limit 128 \
  --security-opt no-new-privileges --cap-drop ALL \
  -e POSTGRES_USER=oip_test -e POSTGRES_DB=oip_m7c_test \
  -e POSTGRES_PASSWORD="$password" \
  postgres:17-alpine@sha256:3540c0362c809df084ffac0ae69fe794515f9de92692f02178bcdce0ef0302ac)"

ready=0
for ((i=0; i<60; i++)); do
  if docker exec "$cid" pg_isready -U oip_test -d oip_m7c_test >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != '1' ]]; then
  echo 'PostgreSQL 17 disposable container did not become ready' >&2
  exit 1
fi

# An explicit required flag changes a missing DB from SKIP to FAIL.
export OIP_M7C_REQUIRE_DATABASE=1
export OIP_M7C_TEST_DSN="postgresql+psycopg://oip_test:${password}@127.0.0.1:15432/oip_m7c_test"
cd "$root"
PYTHONPATH="$root:$root/backend${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m pytest -q -rs backend/tests/test_m7c_postgres17.py backend/tests/test_m7c_safety.py
