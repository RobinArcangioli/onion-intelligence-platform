#!/usr/bin/env bash
# Creates a unique production .env file without printing secrets or replacing an existing one.
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
[[ "$(id -u)" -eq 0 ]] || { echo 'NO-GO: run under sudo/root' >&2; exit 1; }
[[ -f "$ROOT/compose.yaml" && -f "$ROOT/.env.example" ]] || { echo 'NO-GO: run from an OIP source tree' >&2; exit 1; }
[[ ! -e "$ROOT/.env" && ! -L "$ROOT/.env" ]] || { echo 'NO-GO: .env already exists; refusing to overwrite it' >&2; exit 1; }
python3 - "$ROOT/.env" <<'PY'
import os
from pathlib import Path
import secrets
import sys

path = Path(sys.argv[1])
text = (
    '# Generated locally on the VPS. Never send this file or commit it.\n'
    'OIP_DB_USER=oip\n'
    'OIP_DB_NAME=oip\n'
    f'OIP_DB_PASSWORD={secrets.token_hex(32)}\n'
    f'OIP_API_KEY={secrets.token_hex(32)}\n'
    'OIP_LEGACY_API_KEY_ENABLED=false\n'
)
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, 'O_NOFOLLOW'):
    flags |= os.O_NOFOLLOW
fd = os.open(path, flags, 0o600)
with os.fdopen(fd, 'w', encoding='utf-8') as output:
    output.write(text)
PY
chmod 600 "$ROOT/.env"
printf 'PASS: unique OIP secrets created in root-owned .env (0600); nothing printed.\n'
