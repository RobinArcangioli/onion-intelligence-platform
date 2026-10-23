#!/usr/bin/env bash
# Read-only local smoke test. Token is optional; never prints it or sends to remote hosts.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
base='http://127.0.0.1:8000'
for endpoint in /api/health /api/ready; do
  curl --fail --silent --show-error --max-time 10 "$base$endpoint" > /dev/null
  printf 'PASS: %s\n' "$endpoint"
done

# HTTP 401 is intentional: anonymous operators cannot enumerate protected data.
status="$(curl --silent --show-error --max-time 10 -o /dev/null -w '%{http_code}' "$base/api/v1/sources")"
[[ "$status" == '401' ]] || { echo "FAIL: unauthenticated listing returned $status (expected 401)" >&2; exit 1; }
printf 'PASS: anonymous source listing denied\n'

# Check that the gateway serves the actual browser entrypoint.
curl --fail --silent --show-error --max-time 10 "$base/" | grep -qi '<html' || {
  echo 'FAIL: dashboard HTML not served' >&2; exit 1;
}
printf 'PASS: dashboard HTML served locally\n'

if [[ -n "${OIP_SMOKE_TOKEN:-}" ]]; then
  # Stdlib HTTP client keeps the token out of curl argv and command output.
  python3 - <<'PY'
import os
import urllib.request
base = 'http://127.0.0.1:8000'
token = os.environ['OIP_SMOKE_TOKEN']
for route in ('/api/v1/auth/me', '/api/v1/sources', '/api/v1/alerts', '/api/v1/reports'):
    request = urllib.request.Request(base + route, headers={'X-API-Key': token, 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.status == 200
    print('PASS: authenticated ' + route)
PY
else
  echo 'SKIP: authenticated checks (OIP_SMOKE_TOKEN not set)'
fi
printf 'PASS: local smoke completed (no data mutations)\n'
