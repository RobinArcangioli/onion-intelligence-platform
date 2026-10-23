#!/usr/bin/env bash
# One-command local lot-8 validation. No Onion sites visited, no app data deleted.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

printf '\n[1/6] Compose configuration\n'
docker compose config --quiet
printf '\n[2/6] Offline backend regression tests\n'
docker compose --profile test run --build --rm tests
printf '\n[3/6] Build and start local API/dashboard\n'
docker compose up --build -d
printf '\n[4/6] Local gateway and RBAC smoke\n'
bash scripts/smoke-local.sh
printf '\n[5/6] Runtime network boundary (no Onion collection)\n'
docker compose --profile tor up --build -d tor
bash scripts/check-network-isolation.sh
printf '\n[6/6] Temporary PostgreSQL backup/restore rehearsal\n'
bash scripts/check-backup-restore.sh
printf '\nPASS: lot 8 operational checks completed (optional browser/dependency audits remain).\n'
