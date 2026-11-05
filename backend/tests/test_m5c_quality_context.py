"""Offline M5-C documentary quality, human review history, and co-occurrence."""
import asyncio
from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import func, select

from app.collector.runner import collect_one
from app.collector.transport import Fetched
from app.cti.quality import mention_quality, RUBRIC_VERSION
from app.models import AuditLog, IocCandidate, Operator, OperatorToken, ThreatIndicator
from app.security.api_key import fingerprint
from tests.test_tor_collection import API_HEADERS, enabled, onion

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
CONTENT = b"Public advisory references CVE-2025-12345. domain: alert.example.org"


def test_quality_is_explainable_and_does_not_change_raw_confidence():
    at = NOW - timedelta(days=7)
    pending = mention_quality(confidence=65, review_status="PENDING", observed_at=at, as_of=NOW)
    reviewed = mention_quality(confidence=65, review_status="ACCEPTED", observed_at=at, as_of=NOW)
    rejected = mention_quality(confidence=65, review_status="REJECTED", observed_at=at, as_of=NOW)
    assert (pending.score, reviewed.score, rejected.score) == (60, 75, 0)
    assert "MENTION_REVIEWED" in reviewed.explanation_codes
    assert pending.rubric_version == RUBRIC_VERSION


def test_quality_freshness_has_bounded_caps_and_future_clamped():
    assert mention_quality(confidence=100, review_status="ACCEPTED",
                           observed_at=NOW - timedelta(days=30), as_of=NOW).score == 50
    old = mention_quality(confidence=100, review_status="ACCEPTED",
                          observed_at=NOW - timedelta(days=90), as_of=NOW)
    assert old.score == 30 and old.freshness == "STALE" and old.age_days == 90
    future = mention_quality(confidence=50, review_status="PENDING",
                             observed_at=NOW + timedelta(days=1), as_of=NOW)
    assert future.age_days == 0
    assert mention_quality(confidence=1010, review_status="ACCEPTED",
                           observed_at=NOW, as_of=NOW).score == 90
    assert mention_quality(confidence=-3, review_status="REJECTED",
                           observed_at=NOW, as_of=NOW).score == 0


def test_quality_utc_naive_dates_support_sqlite_legacy_and_reject_naive_reference_clock():
    from pytest import raises
    a = mention_quality(confidence=50, review_status="PENDING",
                        observed_at=datetime(2026, 10, 23), as_of=NOW)
    assert a.age_days == 1
    with raises(ValueError):
        mention_quality(confidence=50, review_status="PENDING",
                        observed_at=NOW, as_of=datetime(2026, 10, 24))


async def synthetic_fetch(_url):
    return Fetched(200, "text/plain", "utf-8", CONTENT)


def collect(client, factory, url, monkeypatch):
    monkeypatch.setenv("OIP_IOC_EXTRACTION_ENABLED", "yes")
    sid = enabled(client, url)
    _, state = asyncio.run(collect_one(uuid.UUID(sid), factory, fetcher=synthetic_fetch))
    assert state == "COMPLETED"
    return sid


def candidates(client):
    return client.get("/api/v1/cti/ioc-candidates", headers=API_HEADERS).json()["items"]


def refs(client):
    return client.get("/api/v1/cti/indicators?indicator_type=PUBLIC_CVE_REFERENCE", headers=API_HEADERS).json()["items"]


def accept(client, kind, row):
    if kind == "IOC":
        target = f'/api/v1/cti/ioc-candidates/{row["id"]}/review'
        payload = {"decision": "ACCEPTED", "reason_code": "PUBLIC_REFERENCE_CONFIRMED",
                   "analyst_priority": "LOW"}
    else:
        target = f'/api/v1/cti/indicators/{row["id"]}/review'
        payload = {"decision": "ACCEPTED", "reason": "Reference noted in synthetic public test document",
                   "analyst_priority": "HIGH"}
    result = client.post(target, headers=API_HEADERS, json=payload)
    assert result.status_code == 200, result.text
    return result.json()


def test_quality_preview_separates_rubric_confidence_and_priority(client, db_session_factory, valid_onion_url, monkeypatch):
    collect(client, db_session_factory, valid_onion_url, monkeypatch)
    ioc = candidates(client)[0]
    cve = refs(client)[0]
    accept(client, "IOC", ioc)
    accept(client, "CVE", cve)
    response = client.get("/api/v1/cti/quality-preview?kind=IOC", headers=API_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["rubric_version"] == RUBRIC_VERSION and data["total"] == 1
    row = data["items"][0]
    assert row["original_confidence"] == ioc["confidence"]
    assert row["analyst_priority"] == "LOW"
    assert row["documentary_quality"] >= row["original_confidence"]
    assert "compromise" in data["disclaimer"]
    cve_quality = client.get("/api/v1/cti/quality-preview?kind=CVE", headers=API_HEADERS).json()["items"][0]
    assert cve_quality["analyst_priority"] == "HIGH"
    assert cve_quality["rubric_version"] == RUBRIC_VERSION
    assert cve_quality["reference"] == "CVE-2025-12345"
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action.in_(["ioc_candidate.review", "indicator.review"]))) == 2


def test_correlations_require_both_human_acceptances_and_same_observation(client, db_session_factory, valid_onion_url, monkeypatch):
    collect(client, db_session_factory, valid_onion_url, monkeypatch)
    ioc, cve = candidates(client)[0], refs(client)[0]
    url = '/api/v1/cti/cve-ioc-links'
    assert client.get(url, headers=API_HEADERS).json()['total'] == 0
    accept(client, 'IOC', ioc)
    assert client.get(url, headers=API_HEADERS).json()['total'] == 0
    accept(client, 'CVE', cve)
    result = client.get(url, headers=API_HEADERS)
    assert result.status_code == 200
    row = result.json()['items'][0]
    assert row['cve'] == 'CVE-2025-12345'
    assert row['ioc_value'] == 'alert.example.org'
    assert row['source_count'] == row['observation_count'] == 1
    assert result.json()['relation'] == 'SAME_OBSERVATION_ONLY'
    assert 'compromise' in result.json()['disclaimer']
    collect(client, db_session_factory, onion(29), monkeypatch)
    accept(client, 'IOC', next(x for x in candidates(client) if x['review_status'] == 'PENDING'))
    accept(client, 'CVE', next(x for x in refs(client) if x['review_status'] == 'PENDING'))
    assert client.get(url, headers=API_HEADERS).json()['items'][0]['source_count'] == 2
    assert client.get(url+'?reference=cve-2025-12345', headers=API_HEADERS).json()['total'] == 1
    assert client.get(url+'?reference=CVE-2025-123', headers=API_HEADERS).status_code == 422
    assert client.get(url+'?indicator_type=URL', headers=API_HEADERS).status_code == 422


def test_same_source_different_observations_not_joined(client, db_session_factory, valid_onion_url, monkeypatch):
    # Same source but two different observations: no fabricated link.
    monkeypatch.setenv("OIP_IOC_EXTRACTION_ENABLED", "yes")
    sid = enabled(client, valid_onion_url)
    async def only_cve(_): return Fetched(200, 'text/plain', 'utf-8', b'Public advisory CVE-2025-12345.')
    async def only_ioc(_): return Fetched(200, 'text/plain', 'utf-8', b'domain: alert.example.org')
    for fetch in (only_cve, only_ioc):
        _, state = asyncio.run(collect_one(uuid.UUID(sid), db_session_factory, fetcher=fetch))
        assert state == 'COMPLETED'
    accept(client, 'IOC', candidates(client)[0])
    accept(client, 'CVE', refs(client)[0])
    assert client.get('/api/v1/cti/cve-ioc-links', headers=API_HEADERS).json()['total'] == 0


def test_history_is_whitelisted_and_omits_free_text_and_indicator(client, db_session_factory, valid_onion_url, monkeypatch):
    collect(client, db_session_factory, valid_onion_url, monkeypatch)
    ioc, cve = candidates(client)[0], refs(client)[0]
    accept(client, "IOC", ioc)
    accept(client, "CVE", cve)
    for kind, row in (("IOC", ioc), ("CVE", cve)):
        result = client.get(f'/api/v1/cti/review-history/{kind}/{row["id"]}', headers=API_HEADERS)
        assert result.status_code == 200
        assert result.json()['total'] == 1
        record = result.json()['items'][0]
        assert record['decision'] == 'ACCEPTED'
        assert record['analyst_priority'] in {'LOW', 'HIGH'}
        assert 'free_text' not in str(result.json())
        assert 'Reference noted' not in str(result.json())
        assert 'alert.example.org' not in str(result.json())
        assert 'secret' not in str(result.json())
    assert client.get(f'/api/v1/cti/review-history/OTHER/{ioc["id"]}', headers=API_HEADERS).status_code == 422
    assert client.get(f'/api/v1/cti/review-history/IOC/{uuid.uuid4()}', headers=API_HEADERS).status_code == 404


def test_viewer_cannot_access_quality_links_or_review_history(client, db_session_factory, valid_onion_url, monkeypatch):
    collect(client, db_session_factory, valid_onion_url, monkeypatch)
    tok = 'oip_' + 'q'*44
    with db_session_factory() as db:
        operator = Operator(username='m5c_viewer', role='VIEWER')
        db.add(operator)
        db.flush()
        db.add(OperatorToken(operator_id=operator.id, token_hash=fingerprint(tok),
                             expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
        db.commit()
    routes = ['/api/v1/cti/quality-preview', '/api/v1/cti/cve-ioc-links',
              f'/api/v1/cti/review-history/IOC/{candidates(client)[0]["id"]}']
    for path in routes:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={'X-API-Key':tok}).status_code == 403


def test_pagination_invalid_and_readonly(client, db_session_factory, valid_onion_url, monkeypatch):
    collect(client, db_session_factory, valid_onion_url, monkeypatch)
    urls=['/api/v1/cti/quality-preview?kind=BAD', '/api/v1/cti/quality-preview?limit=51',
          '/api/v1/cti/quality-preview?offset=10001', '/api/v1/cti/cve-ioc-links?limit=51',
          '/api/v1/cti/cve-ioc-links?offset=10001',
          f'/api/v1/cti/review-history/IOC/{candidates(client)[0]["id"]}?limit=51']
    for url in urls:
        assert client.get(url, headers=API_HEADERS).status_code == 422, url
    with db_session_factory() as db:
        before=(db.scalar(select(func.count()).select_from(ThreatIndicator)),
                db.scalar(select(func.count()).select_from(IocCandidate)))
    for path in ['/api/v1/cti/quality-preview','/api/v1/cti/quality-preview?kind=CVE',
                 '/api/v1/cti/cve-ioc-links']:
        assert client.get(path, headers=API_HEADERS).status_code == 200
    with db_session_factory() as db:
        after=(db.scalar(select(func.count()).select_from(ThreatIndicator)),
               db.scalar(select(func.count()).select_from(IocCandidate)))
    assert before == after
