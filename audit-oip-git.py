#!/usr/bin/env python3
"""Audit OIP's staged Git index and complete reachable Git history, read-only.

Run with cwd set to the repository. Never prints credential values, reads .env
from the working tree, rewrites commits, or uses the network.
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

MAX_SCAN_BYTES = 4 * 1024 * 1024
CRITICAL_FILENAMES = frozenset({
    '.env', 'id_rsa', 'id_ed25519', 'credentials', 'credentials.json',
    'known_hosts.private',
})
CRITICAL_SUFFIXES = frozenset({'.pem', '.p12', '.pfx', '.key', '.kdbx', '.dump', '.sqlite', '.sqlite3', '.db'})
CRITICAL_DIRS = frozenset({'backups', 'exports', 'observations', '.ssh', '.aws', 'secrets', 'private'})
NOISE_DIRS = frozenset({
    'node_modules', '__pycache__', '.pytest_cache', '.venv', 'venv',
    'dist', 'test-results', 'playwright-report', '.idea', '.vscode',
    '.ipynb_checkpoints',
})
NOISE_SUFFIXES = frozenset({
    '.log', '.zip', '.7z', '.rar', '.bak', '.swp', '.ipynb',
    '.png', '.jpg', '.jpeg', '.webp', '.mp4', '.mkv',
})
TOKEN_RULES: dict[str, re.Pattern[bytes]] = {
    'private SSH/PEM key': re.compile(rb'-----BEGIN (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----'),
    'GitHub token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9_]{25,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    'GitLab token': re.compile(rb'\bglpat-[A-Za-z0-9_-]{18,}\b'),
    'AWS access ID': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'Slack token': re.compile(rb'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
    'OIP API key assignment': re.compile(rb'(?m)^\s*(?:export\s+)?OIP_API_KEY\s*=\s*["\']?[a-fA-F0-9]{48,}["\']?\s*$'),
    'password-bearing PostgreSQL URL': re.compile(rb'postgres(?:ql)?(?:\+psycopg)?://[^\s@:/]+:[^\s@/${}]{8,}@', re.I),
    'likely literal PostgreSQL password': re.compile(
        rb'(?m)^\s*(?:export\s+)?(?:OIP_DB_PASSWORD|POSTGRES_PASSWORD)\s*=\s*["\']?'
        rb'(?!replace_|example|change_me|test_|dummy|YOUR_|<|\$|\{)[^"\'\s${}#]{16,}["\']?\s*$', re.I),
}


def git(*args: str, payload: bytes | None = None, repo: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ['git', '-C', str(repo), *args], input=payload,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


def check_path(path: str) -> tuple[str, str] | None:
    p = Path(path)
    parts = [x.lower() for x in p.parts]
    name = p.name.lower()
    if (
        name in CRITICAL_FILENAMES
        or (name.startswith('.env.') and name != '.env.example')
        or name.startswith('secrets.')
        or name.endswith(('.secret', '.token'))
        or any(x in CRITICAL_DIRS for x in parts)
        or p.suffix.lower() in CRITICAL_SUFFIXES
    ):
        return ('BLOCK', 'private material or data path')
    if name.endswith(('.zip', '.7z', '.rar', '.tar', '.tar.gz', '.tgz', '.xz', '.zst')):
        return ('BLOCK', 'compressed archive needing separate manual inspection')
    if (
        any(x in NOISE_DIRS for x in parts)
        or p.suffix.lower() in NOISE_SUFFIXES
        or name.startswith('pasted text')
        or name in {'.ds_store', 'thumbs.db'}
    ):
        return ('WARN', 'generated/archived or nonessential path')
    if path.startswith('docs/') and re.match(r'^docs/\d\d-', path):
        return ('NOTE', 'historical development documentation')
    return None


def secret_matches(data: bytes) -> list[str]:
    if b'\x00' in data[:8192]:
        return []  # Binary blobs are called out separately where relevant.
    return [name for name, pattern in TOKEN_RULES.items() if pattern.search(data)]


def main() -> int:
    repo = Path.cwd().resolve()
    root = git('rev-parse', '--show-toplevel', repo=repo)
    if root.returncode or Path(root.stdout.decode().strip()).resolve() != repo:
        print('ERREUR: exécuter depuis la racine du dépôt Git (cd ~/onion-intelligence-platform).')
        return 2

    print('AUDIT GIT OIP — lecture seule, aucun secret affiché, aucun accès réseau')
    print(f'Dépôt : {repo}')
    critical: set[str] = set()
    warnings: set[str] = set()
    historic_notes: set[str] = set()

    stat = git('status', '--porcelain', repo=repo)
    if stat.returncode:
        print('ERREUR: impossible de lire git status.')
        return 2
    if stat.stdout:
        warnings.add('Dépôt avec modifications locales : auditer à nouveau après git add/commit du nettoyage.')

    index = git('ls-files', '--stage', '-z', repo=repo)
    if index.returncode:
        print('ERREUR: impossible de lire l’index Git.')
        return 2
    staged_oids: dict[str, str] = {}
    for entry in index.stdout.split(b'\0'):
        if not entry:
            continue
        meta, _, rawpath = entry.partition(b'\t')
        fields = meta.decode('ascii', 'replace').split()
        if len(fields) != 3 or not rawpath:
            critical.add('Index Git incompréhensible : entrée mal formée')
            continue
        _mode, oid, stage = fields
        path = rawpath.decode('utf-8', 'surrogateescape')
        if stage != '0':
            critical.add(f'INDEX: conflit non résolu : {path}')
        staged_oids[path] = oid
        finding = check_path(path)
        if finding:
            kind, reason = finding
            if kind == 'BLOCK':
                critical.add(f'INDEX: {reason}: {path}')
            elif kind == 'WARN':
                warnings.add(f'INDEX: {reason}: {path}')
    print(f'Index : {len(staged_oids)} chemins suivis')
    if 'frontend/package-lock.json' not in staged_oids:
        warnings.add('INDEX: frontend/package-lock.json absent (build reproductible à contrôler).')

    refs = git('for-each-ref', '--format=%(refname)', repo=repo)
    if refs.returncode:
        critical.add('Impossible de lister les références Git')
        ref_count = 0
    else:
        ref_count = len(refs.stdout.splitlines())

    commits = git('rev-list', '--all', 'HEAD', repo=repo)
    if commits.returncode:
        critical.add('Impossible de lister les commits Git')
        commit_oids: list[str] = []
    else:
        commit_oids = list(dict.fromkeys(s.decode('ascii') for s in commits.stdout.splitlines()))
    print(f'Historique : {len(commit_oids)} commits accessibles, {ref_count} références locales')

    objects = git('rev-list', '--objects', '--all', 'HEAD', repo=repo)
    object_paths: dict[str, str] = {}
    if objects.returncode:
        critical.add('Impossible de lister les objets Git')
    else:
        for row in objects.stdout.splitlines():
            oid_bytes, _, path_bytes = row.partition(b' ')
            oid = oid_bytes.decode('ascii', 'replace')
            path = path_bytes.decode('utf-8', 'surrogateescape')
            object_paths.setdefault(oid, path)
            if not path:
                continue
            finding = check_path(path)
            if not finding:
                continue
            kind, reason = finding
            if kind == 'BLOCK':
                critical.add(f'HISTORIQUE: {reason}: {path} (objet {oid[:12]})')
            elif kind == 'WARN':
                warnings.add(f'HISTORIQUE: {reason}: {path} (objet {oid[:12]})')
            else:
                historic_notes.add(path)
    print(f'Objets Git accessibles : {len(object_paths)}')

    inspected = 0
    skipped_large = 0
    if object_paths:
        batch = git('cat-file', '--batch-check=%(objectname) %(objecttype) %(objectsize)',
                    payload=('\n'.join(object_paths) + '\n').encode(), repo=repo)
        if batch.returncode:
            critical.add('Impossible de connaître la taille des objets')
        else:
            for line in batch.stdout.splitlines():
                cols = line.decode('ascii', 'replace').split()
                if len(cols) != 3 or cols[1] != 'blob':
                    continue
                oid, _, size_str = cols
                size = int(size_str)
                label = f'{object_paths.get(oid, "chemin inconnu")} (objet {oid[:12]})'
                if size > MAX_SCAN_BYTES:
                    skipped_large += 1
                    warnings.add(f'Blob > 4 Mio non analysé : {label}, taille={size} octets')
                    continue
                content = git('cat-file', 'blob', oid, repo=repo)
                if content.returncode:
                    critical.add(f'Blob illisible : {label}')
                    continue
                inspected += 1
                for kind in secret_matches(content.stdout):
                    critical.add(f'HISTORIQUE: secret potentiel ({kind}) : {label} [valeur masquée]')

    # Index blobs may be new and therefore absent from the reachable history.
    scanned_index = 0
    for path, oid in staged_oids.items():
        if oid in object_paths:
            continue
        content = git('cat-file', 'blob', oid, repo=repo)
        if content.returncode:
            critical.add(f'INDEX: blob illisible : {path}')
        elif len(content.stdout) > MAX_SCAN_BYTES:
            warnings.add(f'INDEX: blob > 4 Mio non analysé : {path}')
        else:
            scanned_index += 1
            for kind in secret_matches(content.stdout):
                critical.add(f'INDEX: secret potentiel ({kind}) : {path} [valeur masquée]')

    # Commit messages and annotated tag messages can also leak secrets.
    for oid in commit_oids:
        data = git('cat-file', 'commit', oid, repo=repo)
        if data.returncode:
            critical.add(f'Commit illisible : {oid[:12]}')
            continue
        _header, _sep, message = data.stdout.partition(b'\n\n')
        for kind in secret_matches(message):
            critical.add(f'MESSAGE de commit {oid[:12]} : secret potentiel ({kind}) [valeur masquée]')

    integrity = git('fsck', '--full', '--no-reflogs', '--no-unreachable', repo=repo)
    if integrity.returncode:
        critical.add('git fsck : intégrité des objets Git à vérifier')

    print(f'Analyse de contenu : {inspected} blobs historiques, {scanned_index} blobs index supplémentaires, {skipped_large} grands blobs ignorés')
    if historic_notes:
        print(f'NOTE: {len(historic_notes)} anciennes notes de développement existent dans des commits; '
              'elles ne bloquent pas la conservation de l’historique.')
    print(f'Alertes : {len(critical)} bloquante(s), {len(warnings)} avertissement(s)')
    for alert in sorted(critical):
        print('BLOQUANT: ' + alert)
    for warning in sorted(warnings):
        print('À VÉRIFIER: ' + warning)

    if critical:
        print('RÉSULTAT : STOP — ne pas pousser avant revue et traitement des alertes bloquantes.')
        return 1
    print('RÉSULTAT : aucun secret reconnu ni chemin privé détecté dans les objets inspectés.')
    print('IMPORTANT: audit heuristique, pas une preuve absolue. Revoir les avertissements et, idéalement, compléter par Gitleaks.')
    print('Aucun commit, tag, fichier ou configuration n’a été modifié.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
