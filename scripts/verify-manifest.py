#!/usr/bin/env python3
"""Verify the release candidate's packaged files; no network, no secrets.

Only entries in RELEASE_SHA256SUMS.txt are examined. Local .env and Git are ignored.
"""
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'RELEASE_SHA256SUMS.txt'
LINE = re.compile(r'^([0-9a-f]{64})  (.+)$')


def main() -> int:
    if not MANIFEST.exists():
        print('BLOCKED: release manifest missing')
        return 1
    count = 0
    for raw in MANIFEST.read_text(encoding='utf-8').splitlines():
        match = LINE.fullmatch(raw)
        if not match:
            print('FAIL: invalid manifest entry')
            return 1
        expected, name = match.groups()
        path = ROOT / name
        if name.startswith('/') or '..' in Path(name).parts or not path.is_file() or path.is_symlink():
            print(f'FAIL: unsafe or missing manifest path: {name}')
            return 1
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            print(f'FAIL: release file was modified: {name}')
            return 1
        count += 1
    print(f'PASS: release manifest ({count} files)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
