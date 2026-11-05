"""M5-A: synthetic, offline CTI triage and evidence-only public CVE correlation."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func

from app.collector.runner import collect_one
from app.collector.transport import Fetched
from app.cti.public_references import canonical_cve
from app.models import AuditLog, Operator, OperatorToken, ThreatIndicator
from app.security.api_key import fingerprint
from tests.test_tor_collection import API_HEADERS, enabled, onion


async def synthetic_fetcher(_url):
    return Fetched(200, "text/plain", "utf-8", b"Public advisory references cve-2025-12345. A news article about this advisory.")


def collect(client, factory, url):
    source_id = enabled(client, url)
    _, state = asyncio.run(collect_one(uuid.UUID(source_id), factory, fetcher=synthetic_fetcher))
    assert state == "COMPLETED"
    return source_id


def test_canonical_public_label_only():
    assert canonical_cve("cve-2025-012345") == "CVE-2025-012345"
    for invalid in ["", " cve-2025-1234", "CVE-2025-1234 ", "CVE-1999-1234", "CVE-2025-123",
                    "CVE-2025-123456789", "http://example.com", "CVE-2025-1234/secret", "CVE-2025-12４5"]:
        assert canonical_cve(invalid) is None


def test_empty_and_invalid_routes(client):
    for endpoint in ["/api/v1/cti/public-references", "/api/v1/cti/public-references/CVE-2025-1234/evidence"]:
        assert client.get(endpoint).status_code == 401
    result = client.get("/api/v1/cti/public-references", headers=API_HEADERS).json()
    assert result["total"] == 0
    assert client.get("/api/v1/cti/public-references?reference=CVE-2025-123", headers=API_HEADERS).status_code == 422
    assert client.get("/api/v1/cti/public-references/wrong/evidence", headers=API_HEADERS).status_code == 422
    assert client.get("/api/v1/cti/public-references?limit=101", headers=API_HEADERS).status_code == 422
    assert client.get("/api/v1/cti/public-references/CVE-2025-1234/evidence?offset=10001", headers=API_HEADERS).status_code == 422


def test_cross_source_mentions_are_not_corrob_claims(client, valid_onion_url, db_session_factory):
    a = collect(client, db_session_factory, valid_onion_url)
    b = collect(client, db_session_factory, onion(63))
    # Same source's second observation increases mentions but not independent sources.
    _, status = asyncio.run(collect_one(uuid.UUID(a), db_session_factory, fetcher=synthetic_fetcher))
    assert status == "COMPLETED"
    summary = client.get("/api/v1/cti/public-references?reference=cve-2025-12345", headers=API_HEADERS)
    assert summary.status_code == 200
    assert summary.json()["total"] == 1
    row = summary.json()["items"][0]
    assert row["reference"] == "CVE-2025-12345"
    assert row["source_count"] == 2 and row["mentions"] == 3 and row["observation_count"] == 3
    assert row["reviewed_mentions"] == 0
    assert "co-occurrence" in summary.json()["disclaimer"].lower()
    evidence = client.get("/api/v1/cti/public-references/cve-2025-12345/evidence?limit=2", headers=API_HEADERS).json()
    assert evidence["total"] == 3 and len(evidence["items"]) == 2
    assert {str(x["source_id"]) for x in evidence["items"]} <= {a, b}
    assert not any("title" in x or "body" in x or "description" in x for x in evidence["items"])
    assert all(x["confidence"] == 65 and x["analyst_priority"] == "UNASSESSED" for x in evidence["items"])


def test_review_accept_audited_and_confidence_independent(client, valid_onion_url, db_session_factory):
    collect(client, db_session_factory, valid_onion_url)
    indicators = client.get("/api/v1/cti/indicators", headers=API_HEADERS).json()["items"]
    ref = next(x for x in indicators if x["indicator_type"] == "PUBLIC_CVE_REFERENCE")
    path = f"/api/v1/cti/indicators/{ref['id']}/review"
    payload = {"decision": "ACCEPTED", "analyst_priority": "HIGH", "reason": "Reference present in approved document"}
    updated = client.post(path, headers=API_HEADERS, json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["review_status"] == "ACCEPTED"
    assert updated.json()["analyst_priority"] == "HIGH"
    assert updated.json()["confidence"] == ref["confidence"]
    assert updated.json()["verification_status"] == "OBSERVED_REFERENCE"
    assert client.post(path, headers=API_HEADERS, json=payload).status_code == 409
    assert client.get('/api/v1/cti/public-references', headers=API_HEADERS).json()['items'][0]['reviewed_mentions'] == 1
    with db_session_factory() as db:
        audits = db.scalars(select(AuditLog).where(AuditLog.action == "indicator.review")).all()
        assert len(audits) == 1 and "Reference present" not in audits[0].details
        assert db.scalar(select(func.count()).select_from(ThreatIndicator)) >= 1


def test_rejection_removes_from_aggregation_but_not_database(client, valid_onion_url, db_session_factory):
    collect(client, db_session_factory, valid_onion_url)
    row = client.get('/api/v1/cti/indicators?indicator_type=PUBLIC_CVE_REFERENCE', headers=API_HEADERS).json()['items'][0]
    endpoint = f"/api/v1/cti/indicators/{row['id']}/review"
    assert client.post(endpoint, headers=API_HEADERS, json={"decision": "REJECTED", "analyst_priority": "HIGH",
                                                           "reason": "Reference not relevant to investigation"}).status_code == 422
    response = client.post(endpoint, headers=API_HEADERS, json={"decision": "REJECTED",
                                                              "reason": "Document is unrelated to case"})
    assert response.status_code == 200
    assert client.get('/api/v1/cti/public-references', headers=API_HEADERS).json()['total'] == 0
    assert client.get('/api/v1/cti/public-references/CVE-2025-12345/evidence', headers=API_HEADERS).json()['total'] == 0
    assert client.get(f"/api/v1/cti/indicators/{row['id']}", headers=API_HEADERS).json()['review_status'] == 'REJECTED'


def test_claim_review_refused(client, valid_onion_url, db_session_factory):
    source = enabled(client, valid_onion_url)
    async def fetch(_url):
        return Fetched(200, 'text/plain', 'utf-8', b'Synthetic example: leaked customer records')
    asyncio.run(collect_one(uuid.UUID(source), db_session_factory, fetcher=fetch))
    row = client.get('/api/v1/cti/indicators', headers=API_HEADERS).json()['items'][0]
    assert row['indicator_type'] == 'DATA_LEAK_CLAIM'
    endpoint = f"/api/v1/cti/indicators/{row['id']}/review"
    assert client.post(endpoint, headers=API_HEADERS, json={"decision": "ACCEPTED", "reason": "Reviewed documentary claim"}).status_code == 409


def test_viewer_cannot_review_public_reference(client, valid_onion_url, db_session_factory):
    collect(client, db_session_factory, valid_onion_url)
    indicator = client.get('/api/v1/cti/indicators?indicator_type=PUBLIC_CVE_REFERENCE', headers=API_HEADERS).json()['items'][0]
    token = 'oip_' + 'v' * 44
    with db_session_factory() as db:
        viewer = Operator(username='viewer-test', role='VIEWER')
        db.add(viewer)
        db.flush()
        db.add(OperatorToken(operator_id=viewer.id, token_hash=fingerprint(token),
                             expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
    endpoint = f"/api/v1/cti/indicators/{indicator['id']}/review"
    assert client.post(endpoint, headers={'X-API-Key': token}, json={'decision': 'ACCEPTED',
                       'reason': 'Reference on a synthetic page'}).status_code == 403
    assert client.get(endpoint.replace('/review', ''), headers={'X-API-Key': token}).status_code == 200


def test_bad_review_inputs_do_not_modify_state(client, valid_onion_url, db_session_factory):
    collect(client, db_session_factory, valid_onion_url)
    indicator = client.get('/api/v1/cti/indicators?indicator_type=PUBLIC_CVE_REFERENCE', headers=API_HEADERS).json()['items'][0]
    endpoint = f"/api/v1/cti/indicators/{indicator['id']}/review"
    for payload in ({'decision': 'VERIFIED', 'reason': 'Meaningful analysis'},
                    {'decision': 'ACCEPTED', 'reason': 'short'},
                    {'decision': 'ACCEPTED', 'reason': ' ' * 11},
                    {'decision': 'ACCEPTED', 'reason': 'x' + ' ' * 12},
                    {'decision': 'ACCEPTED', 'reason': 'Good reason for reviewer', 'token': 'secret'},
                    {'decision': 'ACCEPTED', 'reason': 'Good reason for reviewer', 'analyst_priority': 'CRITICAL'}):
        assert client.post(endpoint, headers=API_HEADERS, json=payload).status_code == 422
    assert client.get(f"/api/v1/cti/indicators/{indicator['id']}", headers=API_HEADERS).json()['review_status'] == 'PENDING'
