#!/usr/bin/env bash
# Explicit ONLINE operation: queries public npm and PyPI vulnerability services.
# Only package names + versions are sent. No onion sources, credentials or observations.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
command -v npm >/dev/null || { echo 'BLOCKED: npm is required on host' >&2; exit 2; }
command -v docker >/dev/null || { echo 'BLOCKED: Docker required' >&2; exit 2; }
if [[ ! -s frontend/package-lock.json ]]; then
  echo 'BLOCKED: frontend/package-lock.json missing. Generate it on a trusted machine: (cd frontend && npm install --package-lock-only --ignore-scripts)' >&2
  exit 2
fi
printf 'Checking npm production and build dependencies (public registry)...\n'
npm --prefix frontend audit --audit-level=high --no-fund
printf 'Checking versions actually installed in the API image (public PyPI advisory source)...\n'
tmpdir="$(mktemp -d)"
umask 077
trap 'rm -rf -- "$tmpdir"' EXIT
# Capture environment from the deployed API rather than guessing versions from loose ranges.
docker compose exec -T api python -m pip freeze \
  | grep -v -i '^onion-intelligence-platform-backend==' > "$tmpdir/installed.txt"
if [[ ! -s "$tmpdir/installed.txt" ]]; then
  echo 'BLOCKED: empty Python dependency inventory' >&2
  exit 2
fi
python3 -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/python" -m pip install --disable-pip-version-check --quiet 'pip-audit>=2.7,<4'
"$tmpdir/venv/bin/python" -m pip_audit -r "$tmpdir/installed.txt" --no-deps --disable-pip
printf 'PASS: npm and Python vulnerability audits (advisory data at time of run)\n'
