#!/usr/bin/env python3
"""Dry-run by default; delete ONLY unchanged RC2 legacy notes on --apply.

No unknown files, runtime configuration, migrations or Git data are removed.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LEGACY = {
    'frontend/README.md': 'b7a0884e4bedb0adf3452006f87b9824e066d856ad572fae07a6a4b9d100a009',
    'scripts/validate-lot8.sh': 'c5f2bbe4b23bcf366d362a59d140a9b13070315bfce5cd9c2ddb35004c772671',
    'docs/00-cadrage.md': '94cf07c897cec8d17ae2ccf9122d3d1ec086b13aade1a7ba55e04deab74c38fe',
    'docs/01-architecture.md': 'dcb2da51c0c12beac0e17cf5348217f3fda20cee4a58c112c061d833f7c44a77',
    'docs/02-modele-donnees.md': 'c80473384713569e6d9145a863d1c450372ca150f5930261aff285f2c4492d7e',
    'docs/03-plan-developpement.md': 'b76fd1b6e7926baa7a2c1bb8cfb89da777dd06c8c459d0bd4a2eafee770794b3',
    'docs/04-validation.md': '6ad39341fde0ed14f3622b5279a0633aa480792d15434413d3100135772f1a21',
    'docs/05-etat-du-projet.md': 'b16f4ab2b14ea64ace56487ab11c00c892c0df8a5be7c32799a3ec613dac6141',
    'docs/06-securite.md': 'f7052c20b5ed87cea3a1dc3cc5306ceb03472d205017aa5a4360f0130e5c7909',
    'docs/07-lot1-gestion-sources.md': '7c55e2f5a91d8c440f3756660d4f344ebaf0cbaa8339233f55aeb6338445855d',
    'docs/08-lot2-collecte-tor.md': '53453cfe48c353e5b1fc1ebabeb49b10a1cc75e9798ce9ecd62c848f4652f6a3',
    'docs/09-lot3-analyse-decouverte.md': 'c3eaf04d48e2106a9bd3d6490e3616581ed1eb0ae5cfb2f06818b6c387989400',
    'docs/10-lot4-cti-classification.md': '29642e0402df6042052e0031a1dc2596cf7a32cec4608d9c7a001e95bce4835d',
    'docs/11-lot5-alertes-rapports.md': 'ef02ebec73a1efd4aae18fc300bb7646921470f65090f117a51c7d4614b09ca3',
    'docs/12-lot6-dashboard-web.md': '1fbf389b5433235256a9590d579132b5bc5a70cb5c87629b285e31279340058d',
    'docs/13-lot7-security-hardening.md': '8332e02a996c1c760991bb84c812a674c4fe0f3666edaded6c04cb23f8f5186a',
    'docs/14-lot8-stabilisation.md': '4dd64dd316ab6801bdbf5e65e11298afb1f5a062acecbe01ed25c07839a312b8',
    'docs/15-checklist-v1.md': '363c3e862c9e3644e36a9ef59e9487740fcb59c873421c529baaf1399483cfb7',
    'docs/16-release-v1-rc1.md': '13fe1d52f4510f1d89160c5c7ff6c4c1b3d4d9a02a76f5ca2421ec07e64f5dde',
    'docs/17-release-checklist.md': '658b787765250684f890f7f9f45fb91539d41f4f54d33349c2fac82575598f5b',
    'docs/17-ui-collecte-manuelle-rc2.md': '250b96a64bcfd68883454ac979792f10206c69ac475ec87b1e31a27a05cd4259',
    'docs/bootstrap-postgresql-preview.sql': '69e6537cc06ba6204b8485fbc9d2ab3c698c643b81a06397e69bb71b550e1910'
}


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['git', '-C', str(ROOT), *args], text=True, capture_output=True, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description='Clean only unchanged v1 RC2 historical notes')
    parser.add_argument('--apply', action='store_true', help='actually remove allowlisted notes')
    args = parser.parse_args()
    if git('rev-parse', '--show-toplevel').returncode:
        print('BLOCKED: execute inside a real Git repository', file=sys.stderr)
        return 2
    conflicts=[];remove=[]
    for rel,expected in LEGACY.items():
        file=ROOT/rel
        if not file.exists():
            continue
        if not file.is_file() or file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest()!=expected:
            conflicts.append(rel)
        else:
            remove.append(rel)
    if conflicts:
        print('BLOCKED: historical files modified; review manually (nothing deleted):',file=sys.stderr)
        for rel in conflicts:print('  '+rel,file=sys.stderr)
        return 1
    for rel in remove:
        print(('REMOVE ' if args.apply else 'WOULD REMOVE ')+rel)
    if not args.apply:
        print(f'DRY RUN: {len(remove)} unchanged legacy files; re-run --apply to clean')
        return 0
    for rel in remove:
        tracked=git('ls-files','--error-unmatch','--',rel).returncode==0
        if tracked:
            result=git('rm','--',rel)
            if result.returncode:
                print('BLOCKED: git rm refused '+rel+'; '+result.stderr.strip(),file=sys.stderr)
                return 1
        else:
            (ROOT/rel).unlink()
    print(f'PASS: removed {len(remove)} unmodified historical files; inspect git diff --cached --stat')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
