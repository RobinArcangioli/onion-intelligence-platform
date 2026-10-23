"""End-to-end synthetic checks: no real Tor access, no production DB access."""
import asyncio
from pathlib import Path
import uuid

from sqlalchemy import func, select

from app.collector.runner import collect_one
from app.collector.transport import CollectError, Fetched
from app.models import CrawlJob, SourceObservation, DiscoveredOnion, Alert
from app.security import network_probe
from tests.test_tor_collection import API_HEADERS, enabled, onion
from tests.test_alerts_reports_lot5 import period


def test_full_local_cti_journey(client, valid_onion_url, db_session_factory):
    """One approved synthetic fetch -> discovery -> alert -> immutable report."""
    source_id = enabled(client, valid_onion_url)
    created = client.post('/api/v1/watchlists', headers=API_HEADERS, json={'name': 'Example Monitoring'})
    assert created.status_code == 201
    watchlist_id = created.json()['id']
    created_rule = client.post(f'/api/v1/watchlists/{watchlist_id}/rules',
                               headers=API_HEADERS, json={'phrase': 'Example Inc', 'weight': 30})
    assert created_rule.status_code == 201
    discovered = onion(122)
    calls = []

    async def fake_fetch(url):
        calls.append(url)
        return Fetched(200, 'text/html', 'utf-8', (
            f'<title>Public news</title><main>Example Inc ransomware leak CVE-2025-12345</main>'
            f'<a href="{discovered}">reference</a>'
        ).encode())

    job_id, outcome = asyncio.run(collect_one(uuid.UUID(source_id), db_session_factory, fetcher=fake_fetch))
    assert outcome == 'COMPLETED'
    assert calls == [valid_onion_url], 'No automatic navigation to discovered links'
    discovered_rows = client.get('/api/v1/collection/discoveries', headers=API_HEADERS).json()
    assert discovered_rows['total'] == 1
    assert discovered_rows['items'][0]['status'] == 'PENDING'
    signals = client.get('/api/v1/alerts', headers=API_HEADERS).json()
    assert signals['total'] >= 1
    assert all(item['verification_status'] != 'CONFIRMED_PUBLIC_INFORMATION'
               for item in signals['items'])

    report = client.post('/api/v1/reports', headers=API_HEADERS, json={**period(), 'source_id': source_id})
    assert report.status_code == 201
    rid = report.json()['id']
    snapshot = client.get(f'/api/v1/reports/{rid}/export?format=json', headers=API_HEADERS)
    assert snapshot.status_code == 200
    assert snapshot.json()['totals']['observations'] == 1
    assert 'ransomware leak' not in snapshot.text
    assert '.onion' not in snapshot.text
    with db_session_factory() as db:
        assert db.get(CrawlJob, job_id).status == 'COMPLETED'
        assert db.scalar(select(func.count()).select_from(SourceObservation)) == 1
        assert db.scalar(select(func.count()).select_from(DiscoveredOnion)) == 1
        assert db.scalar(select(func.count()).select_from(Alert)) == signals['total']


def test_transport_failure_is_recorded_as_error_code_only(client, valid_onion_url, db_session_factory):
    source_id = enabled(client, valid_onion_url)

    async def unavailable(_url):
        raise CollectError('TOR_NETWORK_ERROR')

    job_id, state = asyncio.run(collect_one(uuid.UUID(source_id), db_session_factory, fetcher=unavailable))
    assert state == 'FAILED'
    with db_session_factory() as db:
        job = db.get(CrawlJob, job_id)
        assert job.error_code == 'TOR_NETWORK_ERROR'
        assert db.scalar(select(func.count()).select_from(SourceObservation)) == 0
        assert db.scalar(select(func.count()).select_from(DiscoveredOnion)) == 0


def test_network_probe_success_and_failure_without_any_network(monkeypatch, capsys):
    # Four fixed endpoints: Tor, DB, IPv4 HTTPS and IPv4 DNS.
    success = {('tor', 9050): True, ('db', 5432): True,
               ('1.1.1.1', 443): False, ('8.8.8.8', 53): False}
    monkeypatch.setattr(network_probe, 'reachable', lambda host, port: success[(host, port)])
    assert network_probe.main() == 0
    assert capsys.readouterr().out.count('PASS:') == 4
    success[('1.1.1.1', 443)] = True
    assert network_probe.main() == 1
    assert 'FAIL: Direct IPv4 HTTPS denied' in capsys.readouterr().out
    success[('1.1.1.1', 443)] = False
    success[('tor', 9050)] = False
    assert network_probe.main() == 1


def test_smoke_and_restore_scripts_are_read_only_or_disposable():
    import os
    root = Path(os.environ.get('OIP_TEST_REPO_ROOT', str(Path(__file__).resolve().parents[2])))
    for script in ('scripts/smoke-local.sh', 'scripts/check-network-isolation.sh',
                   'scripts/check-backup-restore.sh'):
        text = (root / script).read_text(encoding='utf-8')
        assert 'set -Eeuo pipefail' in text
        assert 'cat .env' not in text and 'source .env' not in text
    network = (root / 'scripts/check-network-isolation.sh').read_text()
    assert '--no-deps' in network and 'network_probe' in network
    backup = (root / 'scripts/check-backup-restore.sh').read_text()
    assert 'createdb' in backup and 'dropdb' in backup
    assert 'bash scripts/restore-db.sh' not in backup  # Must never call production restore.
    smoke = (root / 'scripts/smoke-local.sh').read_text()
    assert '127.0.0.1:8000' in smoke and 'OIP_SMOKE_TOKEN' in smoke
