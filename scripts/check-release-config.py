#!/usr/bin/env python3
"""Safely inspect resolved docker compose JSON from stdin; never print env values.

Compose output contains credentials. Do not write it to disk or logs.
"""
import json
import sys


def main() -> int:
    try:
        obj = json.load(sys.stdin)
        services = obj['services']
        nets = obj['networks']
        for name in ('db', 'api', 'tor', 'collector', 'queue_worker', 'tests'):
            if services[name].get('ports'):
                raise ValueError(f'{name} publishes a host port')
        gateway_ports = services['gateway'].get('ports', [])
        if len(gateway_ports) != 1:
            raise ValueError('Gateway must publish exactly one port')
        p = gateway_ports[0]
        if not (p.get('host_ip') == '127.0.0.1'
                and str(p.get('published')) == '8000'
                and int(p.get('target', 0)) == 8080):
            raise ValueError('Gateway must bind only 127.0.0.1:8000 -> 8080')
        collector_nets = set(services['collector']['networks'])
        if collector_nets != {'private', 'tor_proxy'}:
            raise ValueError('Collector has unexpected networks')
        worker = services['queue_worker']
        if set(worker['networks']) != {'private', 'tor_proxy'}:
            raise ValueError('Manual queue worker has unexpected networks')
        if set(worker.get('profiles', [])) != {'tor'}:
            raise ValueError('Manual queue worker must remain opt-in')
        if worker.get('privileged') or any('docker.sock' in str(v) for v in worker.get('volumes', [])):
            raise ValueError('Manual queue worker must not control Docker')
        if not worker.get('read_only') or 'ALL' not in worker.get('cap_drop', []):
            raise ValueError('Manual queue worker confinement required')
        for net in ('private', 'tor_proxy'):
            matching = [config for key, config in nets.items() if key.endswith('_' + net) or key == net]
            if not matching or not all(item.get('internal') is True for item in matching):
                raise ValueError(f'{net} network must be internal')
        if services['tests'].get('network_mode') != 'none':
            raise ValueError('Offline backend tests must have network_mode=none')
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f'FAIL: Compose isolation policy: {exc}', file=sys.stderr)
        return 1
    print('PASS: Compose release isolation policy')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
