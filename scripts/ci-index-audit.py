#!/usr/bin/env python3
"""CI-only Git INDEX audit. Does not authorize historical/public publication.

Inspects staged bytes (not working-tree .env) and never prints credential values.
For history/publication decisions use scripts/pre-push-audit.py separately.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
AUDITOR_PATH = ROOT / 'scripts' / 'pre-push-audit.py'


def load_rules():
    spec = importlib.util.spec_from_file_location('oip_existing_audit_rules', AUDITOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError('source audit rules unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=False)


def audit_index(root: Path, rules) -> tuple[int, list[str]]:
    index = git(root, 'ls-files', '--cached', '-z')
    if index.returncode:
        return 0, ['could not read Git index']
    paths = sorted({p.decode('utf-8', 'surrogateescape') for p in index.stdout.split(b'\0') if p})
    issues: list[str] = []
    for required in ('.env.example', 'frontend/package-lock.json'):
        if required not in paths:
            issues.append(f'missing required tracked file: {required}')
    for path in paths:
        if rules.bad_path(path):
            issues.append(f'forbidden tracked path: {path}')
            continue
        result = git(root, 'show', ':' + path)
        if result.returncode:
            issues.append(f'unreadable staged file: {path}')
            continue
        if len(result.stdout) > rules.MAX_BYTES:
            issues.append(f'staged file exceeds safe audit size: {path}')
            continue
        for kind in rules.classify(result.stdout):
            issues.append(f'possible {kind} in {path} (value hidden)')
    diff = git(root, 'diff', '--cached', '--check')
    if diff.returncode:
        issues.append('git diff --cached --check failed')
    return len(paths), issues


def main() -> int:
    try:
        count, issues = audit_index(ROOT, load_rules())
    except (OSError, RuntimeError) as exc:
        print(f'NO-GO: CI index audit unavailable: {type(exc).__name__}', file=sys.stderr)
        return 2
    if issues:
        for item in issues:
            print('NO-GO: ' + item, file=sys.stderr)
        return 1
    print(f'PASS: CI index audit ({count} tracked files, no history examined)')
    print('NOTICE: public publication additionally requires a full historical audit and owner approval')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
