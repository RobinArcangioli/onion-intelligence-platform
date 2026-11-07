#!/usr/bin/env bash
# Controlled, non-destructive OVH P0 deployment: DB+API+UI only; Tor never started.
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$ROOT"

die() { printf 'NO-GO: %s\n' "$*" >&2; exit 1; }
command -v python3 >/dev/null || die 'Python 3 required'
[[ -z "${COMPOSE_PROFILES:-}" ]] || die 'COMPOSE_PROFILES must be unset; this launcher never enables Tor'
# Deliberately ignore COMPOSE_FILE; use audited source + OVH overlay.
compose=(docker compose --project-name onion-intelligence-platform --env-file "$ROOT/.env" \
  -f "$ROOT/compose.yaml" -f "$ROOT/deploy/ovh/compose.private.yaml")

check_env() {
  [[ -f "$ROOT/.env" && ! -L "$ROOT/.env" ]] || die 'Create a regular root .env (not a symlink)'
  local mode
  mode="$(stat -c '%a' "$ROOT/.env")"
  [[ "$mode" == '600' || "$mode" == '400' ]] || die '.env must have mode 0600 or 0400'
  command -v docker >/dev/null || die 'Docker Engine + Compose v2 required'
  docker compose version >/dev/null || die 'Docker Compose v2 required'
}

check() {
  check_env
  # Resolved config contains secrets. Stream directly to validator; NEVER print/save it.
  "${compose[@]}" config --format json | python3 "$ROOT/deploy/ovh/check_compose.py"
}

ensure_tor_stopped() {
  local running
  running="$("${compose[@]}" ps --status running --services 2>/dev/null)" || die 'Cannot inspect running services'
  if grep -Eq '^(tor|collector|queue_worker|scheduler)$' <<< "$running"; then
    die 'Tor/collector/worker already running: stop and investigate BEFORE OVH P0 deployment'
  fi
}

smoke() {
  command -v curl >/dev/null || die 'curl is required for smoke checks'
  for path in /api/health /api/ready /; do
    curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:8000$path" >/dev/null || die "smoke failed: $path"
    printf 'PASS: %s\n' "$path"
  done
  local status
  status="$(curl --silent --show-error --max-time 10 -o /dev/null -w '%{http_code}' 'http://127.0.0.1:8000/api/v1/sources')"
  [[ "$status" == 401 ]] || die "anonymous source listing returned $status (expected 401)"
  printf 'PASS: anonymous source listing denied\n'
  # Does not enqueue or contact any Onion site.
}

case "${1:-}" in
  check)
    check
    ;;
  deploy)
    check
    ensure_tor_stopped
    # Existing PostgreSQL volume => API boot may apply Alembic migrations.
    # Require explicit attestation of a local pre-migration dump.
    if docker volume inspect onion-intelligence-platform_postgres_data >/dev/null 2>&1; then
      [[ "${OIP_LOCAL_MIGRATION_BACKUP_VERIFIED:-}" == yes ]] || die 'Existing DB: verify the local pre-migration dump, then set OIP_LOCAL_MIGRATION_BACKUP_VERIFIED=yes for this invocation'
    fi
    "${compose[@]}" up --build -d db api gateway
    ensure_tor_stopped
    smoke
    printf 'PASS: private core deployed; Tor and manual job enqueue remain disabled\n'
    ;;
  smoke)
    check
    ensure_tor_stopped
    smoke
    ;;
  status)
    check
    "${compose[@]}" ps
    ensure_tor_stopped
    ;;
  *)
    printf 'Usage: %s {check|deploy|smoke|status}\n' "${0##*/}" >&2
    exit 2
    ;;
esac
