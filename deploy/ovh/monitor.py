#!/usr/bin/env python3
"""Local, low-overhead OIP health probe. Never touches Tor or external URLs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler

PROJECT = 'onion-intelligence-platform'
ROOT = Path(__file__).resolve().parents[2]
SERVICES = ('db', 'api', 'gateway')
REQUIRE_BACKUP = os.environ.get('OIP_MONITOR_REQUIRE_BACKUP', '0') == '1'
STAMP = Path('/var/lib/oip-monitor/last-backup-ok')


def docker(*args):
    proc = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=15, check=False)
    if proc.returncode:
        raise RuntimeError('docker command failed')
    return proc.stdout.strip()


def check_containers():
    names = docker('ps', '--format', '{{.Names}}').splitlines()
    for service in SERVICES:
        name = f'{PROJECT}-{service}-1'
        if name not in names:
            raise RuntimeError(f'{service} not running')
        state = json.loads(docker('inspect', '--format', '{{json .State}}', name))
        if not state.get('Running'):
            raise RuntimeError(f'{service} stopped')
        health = state.get('Health')
        if service in ('db', 'api') and (not health or health.get('Status') != 'healthy'):
            raise RuntimeError(f'{service} unhealthy')
        ports = json.loads(docker('inspect', '--format', '{{json .NetworkSettings.Ports}}', name))
        bindings = [entry for mappings in ports.values() if mappings for entry in mappings]
        if service == 'gateway':
            if bindings != [{'HostIp': '127.0.0.1', 'HostPort': '8000'}]:
                raise RuntimeError('gateway port is not private loopback only')
        elif bindings:
            raise RuntimeError(f'{service} publishes a host port')
    for name in names:
        if name.startswith(f'{PROJECT}-') and name.rsplit('-', 1)[0].removeprefix(f'{PROJECT}-') in (
            'tor', 'collector', 'queue_worker'
        ):
            raise RuntimeError('Tor/collection service is running')


def check_http():
    # Never honor environment HTTP_PROXY: all requests are loopback only.
    opener = build_opener(ProxyHandler({}))
    for path in ('/api/health', '/api/ready', '/'):
        try:
            with opener.open('http://127.0.0.1:8000' + path, timeout=5) as response:
                if response.status != 200:
                    raise RuntimeError(f'HTTP {path}: not 200')
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f'HTTP {path}: unavailable') from exc
    try:
        with opener.open('http://127.0.0.1:8000/api/v1/sources', timeout=5) as response:
            status = response.status
    except HTTPError as exc:
        status = exc.code
    except (URLError, TimeoutError) as exc:
        raise RuntimeError('HTTP anonymous check unavailable') from exc
    if status != 401:
        raise RuntimeError(f'anonymous access: got HTTP {status}, expected 401')


def check_resources(disk_percent=85, min_mem_mib=350):
    usage = shutil.disk_usage('/var/lib/docker')
    used_percent = (100 * (usage.total - usage.free)) / usage.total
    if used_percent >= disk_percent:
        raise RuntimeError(f'disk critical: {used_percent:.1f}% >= {disk_percent}%')
    meminfo = Path('/proc/meminfo').read_text(encoding='ascii')
    available = next((int(x.split()[1]) for x in meminfo.splitlines()
                      if x.startswith('MemAvailable:')), None)
    if available is None or available < min_mem_mib * 1024:
        raise RuntimeError(f'available RAM below {min_mem_mib} MiB')
    return round(used_percent, 1), available // 1024


def check_backup(max_age_hours=36, require=REQUIRE_BACKUP, stamp=STAMP):
    if not require:
        return 'NOT_ENABLED'
    if not stamp.is_file() or stamp.is_symlink():
        raise RuntimeError('verified offsite transfer marker missing')
    age = time.time() - stamp.stat().st_mtime
    if age < -300 or age > max_age_hours * 3600:
        raise RuntimeError('offsite transfer is stale')
    return 'RECENT'  # Transfer success only; never proves restoration.


def main():
    checks = [
        ('containers/private ports', check_containers),
        ('local health and authentication', check_http),
        ('host disk/RAM', check_resources),
        ('encrypted offsite transfer freshness', check_backup),
    ]
    errors = 0
    for label, fn in checks:
        try:
            result = fn()
            print(f'PASS {label}: {result if result is not None else "OK"}')
        except Exception as exc:  # Isolate checks; no subprocess stderr or credentials printed.
            errors += 1
            print(f'FAIL {label}: {exc}', file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
