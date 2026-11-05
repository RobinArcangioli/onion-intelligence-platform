"""M5-B: synthetic IOC mentions only; no Tor or external lookups."""
import asyncio
from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import func, select

from app.collector.runner import collect_one
from app.collector.transport import Fetched
from app.cti.ioc_candidates import canonical_ioc, extract_ioc_mentions, extraction_enabled, MAX_IOCS_PER_OBSERVATION
from app.models import Alert, AuditLog, IocCandidate, Operator, OperatorToken
from app.security.api_key import fingerprint
from tests.test_tor_collection import API_HEADERS, enabled, onion

DEMO_HASH = 'A' * 64
DOC = (f'Domain: Alert.Example.Org. ip: 8.8.8.8  ipv6: 2001:4860:4860::8888 '
       f'sha256: {DEMO_HASH} domain: alert.example.org')


def test_canonicalization_is_strict_and_public_only():
    assert canonical_ioc('DOMAIN', 'ALERT.EXAMPLE.ORG.') == 'alert.example.org'
    assert canonical_ioc('IPV4', '8.8.8.8') == '8.8.8.8'
    assert canonical_ioc('IPV6', '2001:4860:4860::8888') == '2001:4860:4860::8888'
    assert canonical_ioc('SHA256', DEMO_HASH) == DEMO_HASH.lower()
    for item in ['http://test.example.org', 'a.local', 'hidden.onion', 'username:password@example.org',
                 'foo..org', 'x-.net', '192.168.0.1', '999.999.999.999', 'a.test', 'localhost']:
        assert canonical_ioc('DOMAIN', item) is None
    for value in ['10.0.0.1', '127.0.0.1', '192.0.2.1', '169.254.1.2', '0.0.0.0', '224.0.0.1']:
        assert canonical_ioc('IPV4', value) is None
    assert canonical_ioc('IPV6', '::1') is None
    assert canonical_ioc('IPV6', 'ff02::1') is None
    assert canonical_ioc('IPV6', '::ffff:8.8.8.8') is None
    assert canonical_ioc('SHA256', 'g' * 64) is None
    assert canonical_ioc('SHA256', 'A' * 65) is None
    assert canonical_ioc('OTHER', '8.8.8.8') is None


def test_explicit_labels_normalize_deduplicate_and_bound():
    mentions = extract_ioc_mentions(DOC)
    assert [(x.indicator_type, x.normalized_value) for x in mentions] == [
        ('DOMAIN', 'alert.example.org'), ('IPV4', '8.8.8.8'),
        ('IPV6', '2001:4860:4860::8888'), ('SHA256', DEMO_HASH.lower())]
    assert all(x.confidence == 50 and x.evidence_code.startswith('M5B_EXPLICIT_') for x in mentions)
    many = ' '.join(f'domain: d{i}.example.org' for i in range(100))
    assert len(extract_ioc_mentions(many)) == MAX_IOCS_PER_OBSERVATION


def test_incidental_values_credentials_and_hidden_hosts_excluded():
    text = ('https://account.example.org:443 user:password@foo.org '
            '8.8.8.8 ' + DEMO_HASH + ' domain: foo.onion domain: host.local '
            'ip: 10.0.0.1 ip: 2001:db8::1 sha256: ' + DEMO_HASH + 'bad '
            'domain: x.example.org/secret ipv4: 8.8.8.8/24')
    assert extract_ioc_mentions(text) == ()


def test_default_disabled_and_unknown_flag_fail_closed(monkeypatch):
    monkeypatch.delenv('OIP_IOC_EXTRACTION_ENABLED', raising=False)
    assert not extraction_enabled()
    monkeypatch.setenv('OIP_IOC_EXTRACTION_ENABLED', 'maybe')
    assert not extraction_enabled()
    monkeypatch.setenv('OIP_IOC_EXTRACTION_ENABLED', 'yes')
    assert extraction_enabled()


async def fetcher(_url):
    return Fetched(200, 'text/plain', 'utf-8', DOC.encode())


def collect(client, factory, url):
    source_id = enabled(client, url)
    _, state = asyncio.run(collect_one(uuid.UUID(source_id), factory, fetcher=fetcher))
    assert state == 'COMPLETED'
    return source_id


def test_collection_is_off_without_opt_in(client, db_session_factory, valid_onion_url, monkeypatch):
    monkeypatch.delenv('OIP_IOC_EXTRACTION_ENABLED', raising=False)
    collect(client, db_session_factory, valid_onion_url)
    assert client.get('/api/v1/cti/ioc-candidates', headers=API_HEADERS).json()['total'] == 0
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(IocCandidate)) == 0


def test_collection_opt_in_persists_only_normalized_references(client, db_session_factory, valid_onion_url, monkeypatch):
    monkeypatch.setenv('OIP_IOC_EXTRACTION_ENABLED', 'yes')
    source_id = collect(client, db_session_factory, valid_onion_url)
    response = client.get('/api/v1/cti/ioc-candidates?limit=10', headers=API_HEADERS)
    assert response.status_code == 200
    assert response.json()['total'] == 4
    items = response.json()['items']
    assert {x['indicator_type'] for x in items} == {'DOMAIN', 'IPV4', 'IPV6', 'SHA256'}
    assert all(x['source_id'] == source_id and x['review_status'] == 'PENDING'
               and x['confidence'] == 50 for x in items)
    with db_session_factory() as db:
        # IOC candidates must not create alerts automatically.
        assert db.scalar(select(func.count()).select_from(Alert)) == 0
        assert db.scalar(select(func.count()).select_from(IocCandidate)) == 4


def test_quarantine_never_persists_derived_iocs(client, db_session_factory, valid_onion_url, monkeypatch):
    monkeypatch.setenv('OIP_IOC_EXTRACTION_ENABLED', '1')
    source_id = enabled(client, valid_onion_url)
    async def sensitive_fetch(_):
        return Fetched(200, 'text/plain', 'utf-8', (DOC + ' child sexual abuse material').encode())
    _, state = asyncio.run(collect_one(uuid.UUID(source_id), db_session_factory, fetcher=sensitive_fetch))
    assert state == 'COMPLETED'
    assert client.get('/api/v1/cti/ioc-candidates', headers=API_HEADERS).json()['total'] == 0


def test_requires_analyst_read_and_review(client, db_session_factory, valid_onion_url, monkeypatch):
    monkeypatch.setenv('OIP_IOC_EXTRACTION_ENABLED', 'yes')
    collect(client, db_session_factory, valid_onion_url)
    candidate = client.get('/api/v1/cti/ioc-candidates', headers=API_HEADERS).json()['items'][0]
    viewer_token = 'oip_' + 'w' * 44
    with db_session_factory() as db:
        viewer = Operator(username='m5b_viewer', role='VIEWER')
        db.add(viewer)
        db.flush()
        db.add(OperatorToken(operator_id=viewer.id, token_hash=fingerprint(viewer_token),
                             expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
    for path in ['/api/v1/cti/ioc-candidates', '/api/v1/cti/ioc-correlations']:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={'X-API-Key': viewer_token}).status_code == 403
    endpoint = f'/api/v1/cti/ioc-candidates/{candidate["id"]}/review'
    assert client.post(endpoint, headers={'X-API-Key': viewer_token}, json={
        'decision': 'ACCEPTED', 'reason_code': 'PUBLIC_REFERENCE_CONFIRMED'}).status_code == 403


def test_review_requires_reason_code_no_free_text(client, db_session_factory, valid_onion_url, monkeypatch):
    monkeypatch.setenv('OIP_IOC_EXTRACTION_ENABLED', 'yes')
    collect(client, db_session_factory, valid_onion_url)
    candidate = client.get('/api/v1/cti/ioc-candidates', headers=API_HEADERS).json()['items'][0]
    endpoint = f'/api/v1/cti/ioc-candidates/{candidate["id"]}/review'
    for payload in [
        {'decision': 'REJECTED', 'reason_code': 'NON_INDICATOR', 'analyst_priority': 'HIGH'},
        {'decision': 'REJECTED', 'reason_code': 'PUBLIC_REFERENCE_CONFIRMED'},
        {'decision': 'ACCEPTED', 'reason_code': 'MISPARSED'},
        {'decision': 'ACCEPTED', 'reason_code': 'PUBLIC_REFERENCE_CONFIRMED', 'free_text': 'secret'},
    ]:
        assert client.post(endpoint, headers=API_HEADERS, json=payload).status_code == 422
    response = client.post(endpoint, headers=API_HEADERS, json={
        'decision': 'ACCEPTED', 'analyst_priority': 'HIGH',
        'reason_code': 'PUBLIC_REFERENCE_CONFIRMED'})
    assert response.status_code == 200, response.text
    assert response.json()['confidence'] == candidate['confidence']
    assert response.json()['analyst_priority'] == 'HIGH'
    assert client.post(endpoint, headers=API_HEADERS, json={
        'decision': 'ACCEPTED', 'reason_code': 'PUBLIC_REFERENCE_CONFIRMED'}).status_code == 409
    with db_session_factory() as db:
        rows = db.scalars(select(AuditLog).where(AuditLog.action == 'ioc_candidate.review')).all()
        assert len(rows) == 1
        assert candidate['normalized_value'] not in rows[0].details


def test_correlations_only_include_reviewed_mentions(client, db_session_factory, valid_onion_url, monkeypatch):
    monkeypatch.setenv('OIP_IOC_EXTRACTION_ENABLED', 'true')
    collect(client, db_session_factory, valid_onion_url)
    collect(client, db_session_factory, onion(55))
    endpoint = '/api/v1/cti/ioc-candidates?indicator_type=DOMAIN'
    candidates = client.get(endpoint, headers=API_HEADERS).json()['items']
    assert len(candidates) == 2
    assert client.get('/api/v1/cti/ioc-correlations', headers=API_HEADERS).json()['total'] == 0
    for candidate in candidates:
        assert client.post(f'/api/v1/cti/ioc-candidates/{candidate["id"]}/review',
                           headers=API_HEADERS, json={'decision': 'ACCEPTED',
                                                     'reason_code': 'PUBLIC_REFERENCE_CONFIRMED'}).status_code == 200
    row = client.get('/api/v1/cti/ioc-correlations?indicator_type=DOMAIN',
                     headers=API_HEADERS).json()['items'][0]
    assert row['source_count'] == 2 and row['mentions'] == 2
    assert row['normalized_value'] == 'alert.example.org'
    assert 'compromise' in client.get('/api/v1/cti/ioc-correlations', headers=API_HEADERS).json()['disclaimer']


def test_rejection_not_in_aggregation(client, db_session_factory, valid_onion_url, monkeypatch):
    monkeypatch.setenv('OIP_IOC_EXTRACTION_ENABLED', 'yes')
    collect(client, db_session_factory, valid_onion_url)
    candidate = client.get('/api/v1/cti/ioc-candidates?indicator_type=DOMAIN', headers=API_HEADERS).json()['items'][0]
    assert client.post(f'/api/v1/cti/ioc-candidates/{candidate["id"]}/review',
                       headers=API_HEADERS, json={'decision': 'REJECTED', 'reason_code': 'MISPARSED'}).status_code == 200
    assert client.get('/api/v1/cti/ioc-correlations?indicator_type=DOMAIN',
                      headers=API_HEADERS).json()['total'] == 0
    assert client.get('/api/v1/cti/ioc-candidates?review_status=REJECTED',
                      headers=API_HEADERS).json()['total'] == 1


def test_invalid_filters_and_limits(client):
    for endpoint in ['/api/v1/cti/ioc-candidates?limit=101',
                     '/api/v1/cti/ioc-candidates?indicator_type=URL',
                     '/api/v1/cti/ioc-candidates?offset=10001',
                     '/api/v1/cti/ioc-correlations?indicator_type=CVE']:
        assert client.get(endpoint, headers=API_HEADERS).status_code == 422
