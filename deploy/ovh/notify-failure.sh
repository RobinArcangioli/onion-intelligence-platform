#!/usr/bin/env bash
# systemd OnFailure handler. No secrets, data or external traffic unless opted in.
set -Eeuo pipefail
unit="${1:-unknown}"
[[ "$unit" =~ ^[a-zA-Z0-9_.@-]+$ ]] || exit 2
echo "OIP ALERT: $unit failed; inspect journalctl -u $unit" >&2
config=/etc/oip/alert.curl
if [[ -f "$config" && ! -L "$config" ]]; then
  [[ "$(stat -c %a "$config")" == 600 && "$(stat -c %u "$config")" == 0 ]] || exit 1
  # The root-only curl config holds the URL/token. It is never used as a CLI arg.
  printf '{"event":"oip_unit_failed","unit":"%s"}' "$unit" |
    curl --fail --silent --show-error --max-time 10 --config "$config" \
      --header 'Content-Type: application/json' --data-binary @- >/dev/null
fi
