#!/usr/bin/env bash
# Run all synthetic browser modes in a network namespace with only loopback.
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "${1:-}" != '--network-ready' ]]; then
  if [[ "${GITHUB_ACTIONS:-}" == true ]]; then
    exec sudo -n unshare --net bash -ec '
      ip link set lo up
      exec runuser -u "$1" -- env "PATH=$2" "PLAYWRIGHT_BROWSERS_PATH=$3" "OIP_E2E_PYTHON=$4" bash "$5" --network-ready
    ' bash "$(id -un)" "$PATH" "${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}" \
      "${OIP_E2E_PYTHON:-$(command -v python3)}" "$root/scripts/test-browser-mvp.sh"
  fi
  exec unshare --user --map-root-user --net bash -ec '
    ip link set lo up
    exec bash "$1" --network-ready
  ' bash "$root/scripts/test-browser-mvp.sh"
fi

if [[ "$(ip -o link show | cut -d: -f2 | xargs)" != lo ]]; then
  echo 'Refusing browser acceptance outside a loopback-only namespace.' >&2
  exit 1
fi
cd "$root/frontend"
unset OIP_E2E_TOKEN OIP_SMOKE_TOKEN
if [[ -z "${OIP_E2E_PYTHON:-}" && -x "$root/.venv/bin/python" ]]; then
  export OIP_E2E_PYTHON="$root/.venv/bin/python"
fi
npm run build
for mode in visitor simulation acceptance; do
  OIP_E2E_MODE="$mode" npx --no-install playwright test --config=playwright.visitor.config.ts
done
