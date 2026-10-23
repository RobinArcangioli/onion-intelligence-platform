#!/usr/bin/env bash
# Runtime smoke check, never starts collection and never contacts Onion addresses.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

command -v docker >/dev/null || { echo 'Docker is required' >&2; exit 2; }
tor_id="$(docker compose --profile tor ps -q tor)"
[[ -n "$tor_id" ]] || { echo 'Tor is not running; start it with --profile tor' >&2; exit 2; }

# Docker's inspect JSON is authoritative for host-side published port mappings.
ports="$(docker inspect --format '{{json .NetworkSettings.Ports}}' "$tor_id")"
python3 - "$ports" <<'PY'
import json
import sys
ports = json.loads(sys.argv[1]) or {}
if any(binding is not None for binding in ports.values()):
    raise SystemExit('FAIL: Tor publishes a host-side port')
print('PASS: Tor publishes no host-side port')
PY

# Exercises the real collector network namespace with collection disabled.
# --no-deps prevents Compose from creating any extra services implicitly.
docker compose --profile tor run --build --rm -T --no-deps \
  -e OIP_TOR_COLLECTION_ENABLED=false \
  --entrypoint python collector -m app.security.network_probe
printf 'PASS: runtime collector network checks completed\n'
