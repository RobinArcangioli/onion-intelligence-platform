#!/usr/bin/env python3
"""Read-only audit of Git index and all reachable local Git history.

Prints paths and classifications only, NEVER matched secret bytes.
Does not fetch, push, rewrite history, or open network connections.
"""
from __future__ import annotations
import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 4 * 1024 * 1024
# Paths that cannot ever be published, even if excluded by .gitignore.
BAD_PARTS = frozenset({'node_modules', '__pycache__', '.pytest_cache', '.venv',
                       'venv', '.git', 'backups', 'exports', 'observations',
                       'dist', 'test-results', 'playwright-report', '.playwright',
                       '.idea', '.vscode', '.ipynb_checkpoints'})
BAD_EXT = frozenset({'.db', '.sqlite', '.sqlite3', '.dump', '.bak', '.zip', '.7z', '.rar',
                     '.pem', '.p12', '.pfx', '.kdbx', '.log', '.key', '.ipynb',
                     '.png', '.jpg', '.jpeg', '.webp', '.mp4', '.mkv', '.swp'})
BAD_NAMES = frozenset({'id_rsa', 'id_ed25519', 'credentials', 'credentials.json',
                       '.ds_store', 'thumbs.db'})
# Each expression deliberately looks for a recognizable credential *shape*.
# Test placeholders, environment variable references and hash digests are excluded.
SECRET_PATTERNS = {
    'private-key-block': re.compile(rb'-----BEGIN (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----'),
    'github-token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9_]{25,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    'aws-access-id': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'slack-token': re.compile(rb'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
    'oip-api-key-assignment': re.compile(rb'(?m)^\s*(?:export\s+)?OIP_API_KEY\s*=\s*["\']?[a-fA-F0-9]{48,}["\']?\s*$'),
    'database-url-with-password': re.compile(rb'postgres(?:ql)?(?:\+psycopg)?://[^\s@:/]+:[^\s@/${}]{8,}@', re.I),
    'literal-private-password': re.compile(rb'(?m)^\s*(?:export\s+)?(?:OIP_DB_PASSWORD|POSTGRES_PASSWORD)\s*=\s*["\']?(?!replace_|example|change_me|test_|dummy)[^"\'\s${}#]{16,}["\']?\s*$', re.I),
}


def git(*args: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(['git', '-C', str(ROOT), *args], input=input_bytes,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def bad_path(path: str) -> bool:
    # Ensure no secrets in top-level or nested config copies.
    p = Path(path)
    parts = p.parts
    name = p.name.lower()
    if (name == '.env' or (name.startswith('.env.') and name != '.env.example')
            or name in BAD_NAMES or name.startswith('pasted text')
            or name.startswith('secrets.') or name.endswith(('.secret', '.token'))):
        return True
    if any(part.lower() in BAD_PARTS for part in parts) or p.suffix.lower() in BAD_EXT:
        return True
    if name.startswith('oip_') and name.endswith('.zip'):
        return True
    return False


def classify(data: bytes) -> list[str]:
    if b'\x00' in data[:4096]:
        return []
    return [kind for kind, expression in SECRET_PATTERNS.items() if expression.search(data)]


def blob(oid: str) -> bytes | None:
    res = git('cat-file', 'blob', oid)
    return res.stdout if res.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(description='Audit Git before publication; no credential values printed')
    parser.add_argument('--no-history', action='store_true', help='faster index-only check (not enough for public push)')
    parser.add_argument('--allow-historical-notes', action='store_true',
                        help='allow obsolete lot docs in old commits (NOT recommended for first public push)')
    args = parser.parse_args()
    if git('rev-parse', '--is-inside-work-tree').returncode:
        print('BLOCKED: run from your actual Git repository, not an extracted ZIP')
        return 2
    errors: set[str] = set()
    warnings: set[str] = set()
    index = git('ls-files', '-z', '--cached')
    if index.returncode:
        print('BLOCKED: cannot inspect Git index')
        return 2
    paths = sorted(set(p.decode('utf-8','surrogateescape') for p in index.stdout.split(b'\x00') if p))
    if not paths:
        warnings.add('Git index is empty: stage intended source files before audit')
    print(f'INDEX: {len(paths)} tracked/staged paths')
    if 'frontend/package-lock.json' not in paths:
        errors.add('INDEX: frontend/package-lock.json is missing (generate and git add it)')
    if '.env.example' not in paths:
        errors.add('INDEX: .env.example must be tracked')
    for path in paths:
        if bad_path(path):
            errors.add(f'INDEX: forbidden tracked path: {path}')
            continue
        # Read the actual staged/index blob, not the possibly different working-tree copy.
        result = git('show', ':' + path)
        if result.returncode:
            errors.add(f'INDEX: cannot read staged path: {path}')
            continue
        if len(result.stdout) > MAX_BYTES:
            errors.add(f'INDEX: too large to inspect safely: {path}')
            continue
        for kind in classify(result.stdout):
            errors.add(f'INDEX: possible {kind} in {path} (value hidden)')

    check = git('diff', '--cached', '--check')
    if check.returncode:
        errors.add('INDEX: git diff --cached --check failed (inspect it locally)')

    # A path in history is not removed by deleting it in HEAD. More importantly,
    # a token in any reachable blob remains retrievable after push.
    if not args.no_history:
        revs = git('rev-list', '--objects', '--all')
        if revs.returncode:
            errors.add('HISTORY: could not list reachable Git objects')
        else:
            objects = {}
            obsolete_docs = 0
            for line in revs.stdout.splitlines():
                oid, _, path_bytes = line.partition(b' ')
                oid_text = oid.decode('ascii', 'replace')
                path = path_bytes.decode('utf-8', 'surrogateescape')
                objects.setdefault(oid_text, path)
                if path and bad_path(path):
                    errors.add(f'HISTORY: forbidden committed path: {path} (object {oid_text[:12]})')
                if path.startswith('docs/') and re.match(r'docs/\d\d-', path):
                    obsolete_docs += 1
            print(f'HISTORY: {len(objects)} reachable objects; historical numbered-doc references: {obsolete_docs}')
            if obsolete_docs:
                msg = 'Historical lot notes remain accessible through old commits/tags. For a clean public initial release, use a NEW public repository with one sanitized root commit; keep private history separately.'
                if args.allow_historical_notes:
                    warnings.add(msg)
                else:
                    errors.add('HISTORY: ' + msg)
            # Check object sizes in a single subprocess, not by spawning thousands of processes.
            batch = git('cat-file', '--batch-check=%(objectname) %(objecttype) %(objectsize)',
                        input_bytes=('\n'.join(objects) + '\n').encode())
            if batch.returncode:
                errors.add('HISTORY: cannot query all object types/sizes')
            else:
                scan_total = 0
                for line in batch.stdout.splitlines():
                    fields = line.decode('ascii', 'replace').split()
                    if len(fields) != 3 or fields[1] != 'blob':
                        continue
                    oid, _, size_s = fields
                    size = int(size_s)
                    path = objects.get(oid, '')
                    if size > MAX_BYTES:
                        errors.add(f'HISTORY: unscanned large blob {oid[:12]} size={size} bytes (path {path or "unknown"})')
                        continue
                    data = blob(oid)
                    if data is None:
                        errors.add(f'HISTORY: unreadable blob {oid[:12]}')
                        continue
                    scan_total += 1
                    for kind in classify(data):
                        errors.add(f'HISTORY: possible {kind} in blob {oid[:12]} ({path or "unknown path"}); value hidden')
                print(f'HISTORY: inspected {scan_total} reachable blobs for high-confidence secret patterns')
    else:
        errors.add('HISTORY: not checked (--no-history); this mode is insufficient to authorize a public push')

    # Warning: remote URLs can themselves contain embedded access tokens.
    remotes = git('remote', '-v')
    if remotes.returncode == 0 and re.search(rb'://[^\s/@]+@', remotes.stdout):
        errors.add('REMOTE: URL embeds credentials; configure credential helper instead')

    for item in sorted(warnings):
        print('WARN: ' + item)
    for item in sorted(errors):
        print('BLOCKED: ' + item)
    if errors:
        print(f'FAIL: pre-push audit found {len(errors)} potential issue(s), values never printed')
        return 1
    print('PASS: no forbidden tracked paths or recognized secrets in checked index/history (not a guarantee)')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
