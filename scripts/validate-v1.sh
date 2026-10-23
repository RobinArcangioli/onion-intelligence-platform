#!/usr/bin/env bash
# Non-destructive v1 candidate validation. No onion sites are contacted.
# Usage: sudo bash scripts/validate-v1.sh [--core | --release]
# --core: operational tests without authenticated-browser/dependency gates.
# --release: fail closed until tokens, lockfile, audits, browser tests and legacy cutover pass.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
mode="${1:---core}"
if [[ "$mode" != '--core' && "$mode" != '--release' ]]; then
  echo 'Usage: scripts/validate-v1.sh [--core|--release]' >&2
  exit 2
fi
printf '[1/8] Compose configuration & isolation\n'
docker compose --profile tor --profile test config --quiet
docker compose --profile tor --profile test config --format json | python3 scripts/check-release-config.py
printf '[2/8] Offline backend regression\n'
docker compose --profile test run --build --rm tests
printf '[3/8] Build/start local services\n'
docker compose up --build -d
printf '[4/8] Local API and UI smoke\n'
bash scripts/smoke-local.sh
printf '[5/8] Real Tor/collector network boundary; no collection\n'
docker compose --profile tor up --build -d tor
bash scripts/check-network-isolation.sh
printf '[6/8] PostgreSQL restore rehearsal into disposable database\n'
bash scripts/check-backup-restore.sh
printf '[7/8] Release packaged file manifest\n'
python3 scripts/verify-manifest.py
if [[ "$mode" == '--core' ]]; then
  printf '\nPASS: core checks. NOT a stable release gate: use --release to audit dependencies and browser.\n'
  exit 0
fi
printf '[8/8] Release gates: named identity, legacy key, npm/Python audits, Playwright\n'
legacy="$(docker compose exec -T api python -c 'from app.core.config import get_settings; print(str(get_settings().legacy_api_key_enabled).lower())')"
if [[ "$legacy" != 'false' ]]; then
  echo 'BLOCKED: legacy API key is enabled. First validate a named ADMIN token, then set OIP_LEGACY_API_KEY_ENABLED=false in .env and recreate api.' >&2
  exit 1
fi
if [[ -z "${OIP_SMOKE_TOKEN:-}" ]]; then
  if [[ ! -r /dev/tty ]]; then
    echo 'BLOCKED: personal API token required; run interactively or provide OIP_SMOKE_TOKEN securely' >&2
    exit 2
  fi
  read -r -s -p 'OIP personal API token (input hidden): ' OIP_SMOKE_TOKEN </dev/tty
  printf '\n'
fi
export OIP_SMOKE_TOKEN
# Must be a named operator, not the legacy key.
python3 - <<'PY'
import os, urllib.request, json
req = urllib.request.Request('http://127.0.0.1:8000/api/v1/auth/me', headers={'X-API-Key': os.environ['OIP_SMOKE_TOKEN']})
with urllib.request.urlopen(req, timeout=10) as res:
    identity = json.load(res)
if identity.get('legacy') is not False or identity.get('role') not in ('VIEWER', 'ANALYST', 'ADMIN'):
    raise SystemExit('BLOCKED: a valid named operator token is required')
print('PASS: named authenticated operator')
PY
bash scripts/smoke-local.sh
bash scripts/audit-dependencies.sh
command -v npm >/dev/null || { echo 'BLOCKED: npm missing' >&2; exit 2; }
# Avoid automatically installing Chromium or running scripts from unknown registries.
[[ -x frontend/node_modules/.bin/playwright ]] || {
  echo 'BLOCKED: install frontend dependencies first: (cd frontend && npm ci --ignore-scripts)' >&2; exit 2;
}
# sudo changes HOME to /root. Prefer Chromium installed by the invoking user,
# without downloading a second browser or recording authentication credentials.
if [[ -z "${PLAYWRIGHT_BROWSERS_PATH:-}" && -n "${SUDO_USER:-}" && "$SUDO_USER" != root ]]; then
  sudo_user_home="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
  if [[ -n "$sudo_user_home" && -d "$sudo_user_home/.cache/ms-playwright" ]]; then
    export PLAYWRIGHT_BROWSERS_PATH="$sudo_user_home/.cache/ms-playwright"
  fi
fi
export OIP_E2E_TOKEN="$OIP_SMOKE_TOKEN"
(cd frontend && npm run test:unit && npm run typecheck && npm run test:e2e)
unset OIP_E2E_TOKEN OIP_SMOKE_TOKEN
printf '\nPASS: local v1 candidate release gates (online advisory data may change).\n'
