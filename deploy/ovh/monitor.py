#!/usr/bin/env python3
"""Probe local OIP services and write only operational diagnostics."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler

PROJECT = 'onion-intelligence-platform'
SERVICES = ('db', 'api', 'gateway')
WORKER_SERVICES = ("tor", "queue_worker")
WORKER_ISSUES = {
    "WORKER_PULSE_STALE": "worker pulse missing or stale",
    "TOR_PROXY_UNAVAILABLE": "local Tor SOCKS endpoint unavailable",
    "QUEUE_LEASE_EXPIRED": "running job has an expired or missing lease",
    "QUEUE_NOT_PROGRESSING": "eligible job waiting at least five minutes",
    "WORKER_CHECK_UNAVAILABLE": "worker queue or database check unavailable",
}


def docker(*args):
    env = {key: value for key, value in os.environ.items() if key not in ("DOCKER_HOST", "DOCKER_CONTEXT")}
    proc = subprocess.run(["docker", "--host", "unix:///var/run/docker.sock", *args],
                          env=env, capture_output=True, text=True, timeout=15, check=False)
    if proc.returncode:
        raise RuntimeError('docker command failed')
    return proc.stdout.strip()


def check_containers(profile="private"):
    services = SERVICES + WORKER_SERVICES if profile == "manual" else SERVICES
    names = docker('ps', '--format', '{{.Names}}').splitlines()
    for service in services:
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
    expected = {f"{PROJECT}-{service}-1" for service in services}
    unexpected = {name for name in names if name.startswith(f"{PROJECT}-")} - expected
    if unexpected:
        raise RuntimeError("unexpected OIP service running (scheduler or Tor/collection profile mismatch)")


def check_gates(profile):
    expected = "1" if profile == "manual" else "0"
    script = ("from app.core.config import get_settings; "
              "print(int(get_settings().manual_collection_enabled))")
    if docker("exec", f"{PROJECT}-api-1", "python", "-c", script) != expected:
        raise RuntimeError("API manual collection gate does not match the monitor profile")


def worker_checks() -> list[str]:
    output = docker("exec", f"{PROJECT}-queue_worker-1", "python", "-m", "app.collector.monitor")
    statuses = output.splitlines()
    if set(statuses) - set(WORKER_ISSUES) - {"COLLECTION_PAUSED"}:
        raise RuntimeError("unrecognized worker diagnostic")
    if "COLLECTION_PAUSED" in statuses:
        print("INFO manual collection paused")
    return [status for status in statuses if status in WORKER_ISSUES]


class LocalOnlyRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_http():
    # Never honor environment HTTP_PROXY: all requests are loopback only.
    opener = build_opener(ProxyHandler({}), LocalOnlyRedirects())
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


def report(failures: dict[str, str], state_path: Path | None) -> int:
    previous = set()
    if state_path is not None:
        if state_path.exists():
            previous = set(json.loads(state_path.read_text(encoding="utf-8")))
        with tempfile.NamedTemporaryFile(mode="w", dir=state_path.parent, delete=False,
                                         encoding="utf-8") as state:
            json.dump(sorted(failures), state)
        os.replace(state.name, state_path)
    alert = False
    for key, detail in failures.items():
        confirmed = state_path is None or key in previous
        alert |= confirmed
        print(f'{"ALERT" if confirmed else "WARN"} {key}: {detail}', file=sys.stderr)
    for key in sorted(previous - failures.keys()):
        print(f"RECOVERED {key}")
    return int(alert)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("private", "manual"),
                        default=os.environ.get("OIP_MONITOR_PROFILE", "private"))
    parser.add_argument("--state-file", type=Path)
    args = parser.parse_args()
    if args.profile not in ("private", "manual"):
        parser.error("invalid monitor profile")
    checks = [
        ("CONTAINERS", lambda: check_containers(args.profile)),
        ("COLLECTION_GATES", lambda: check_gates(args.profile)),
        ("LOCAL_HTTP", check_http),
        ("HOST_RESOURCES", check_resources),
    ]
    failures = {}
    for key, check in checks:
        try:
            result = check()
            print(f'PASS {key}: {result if result is not None else "OK"}')
        except RuntimeError as exc:
            failures[key] = str(exc)
        except Exception:
            failures[key] = "probe unavailable"
    if args.profile == "manual":
        try:
            for code in worker_checks():
                failures[code] = WORKER_ISSUES[code]
            if not set(failures) & WORKER_ISSUES.keys():
                print("PASS WORKER: OK")
        except Exception:
            failures["WORKER_CHECK_UNAVAILABLE"] = WORKER_ISSUES["WORKER_CHECK_UNAVAILABLE"]
    try:
        return report(failures, args.state_file)
    except (OSError, ValueError, TypeError):
        print("ALERT MONITOR_STATE: local state unavailable", file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
