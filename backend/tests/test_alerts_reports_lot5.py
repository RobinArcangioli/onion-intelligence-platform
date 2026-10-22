"""All events synthetic, no Tor network traffic, no raw page retention."""
import asyncio
import csv
from datetime import datetime, timedelta, timezone
import io
import json
import uuid

import pytest
from sqlalchemy import func, select

from app.alerts.engine import RELEVANCE_ALERT_THRESHOLD, emit_observation_alerts
from app.collector.runner import collect_one
from app.collector.transport import Fetched
from app.models import Alert, AuditLog, Report, SourceObservation
from tests.test_tor_collection import API_HEADERS, enabled, onion


def period(*, days=3):
    t = datetime.now(timezone.utc)
    return {"period_start": (t-timedelta(days=days)).isoformat(),
            "period_end": (t+timedelta(hours=2)).isoformat()}


def run_text(source_id, factory, text):
    async def fake_fetcher(_url):
        return Fetched(200, "text/html", "utf-8", ("<html><main>"+text+"</main></html>").encode())
    return asyncio.run(collect_one(uuid.UUID(source_id), factory, fetcher=fake_fetcher))


def test_alert_api_requires_key(client):
    for path in ("/api/v1/alerts", "/api/v1/reports"):
        assert client.get(path).status_code == 401
    assert client.post("/api/v1/reports", json=period()).status_code == 401
    assert client.get(f"/api/v1/reports/{uuid.uuid4()}/export").status_code == 401


def test_alerts_from_watchlist_and_claims(client, valid_onion_url, db_session_factory):
    sid = enabled(client, valid_onion_url)
    wid = client.post("/api/v1/watchlists", headers=API_HEADERS, json={"name":"SampleCorp"}).json()["id"]
    response = client.post(f"/api/v1/watchlists/{wid}/rules", headers=API_HEADERS,
                           json={"phrase":"SampleCorp", "weight": 30})
    assert response.status_code == 201
    jid, status = run_text(sid, db_session_factory,
                           "SampleCorp SampleCorp stolen database ransomware leak CVE-2025-12345")
    assert status == "COMPLETED"
    listing = client.get("/api/v1/alerts", headers=API_HEADERS).json()
    assert listing["total"] >= 3
    types = {x["event_type"] for x in listing["items"]}
    assert "WATCHLIST_MATCH" in types and "CTI_SIGNAL" in types
    assert all(x["verification_status"] != "CONFIRMED_PUBLIC_INFORMATION" for x in listing["items"])
    assert all("SampleCorp" not in str(item) and "stolen database" not in str(item)
               for item in listing["items"])
    assert client.get("/api/v1/alerts?status=OPEN", headers=API_HEADERS).json()["total"] == listing["total"]
    assert client.get("/api/v1/alerts?source_id="+sid, headers=API_HEADERS).json()["total"] == listing["total"]
    assert client.get("/api/v1/alerts?limit=1", headers=API_HEADERS).json()["total"] == listing["total"]
    assert len(client.get("/api/v1/alerts?limit=1", headers=API_HEADERS).json()["items"]) == 1
    assert client.get("/api/v1/alerts?status=FOO", headers=API_HEADERS).status_code == 422
    assert client.get("/api/v1/alerts?limit=0", headers=API_HEADERS).status_code == 422
    assert client.get(f"/api/v1/alerts/{listing['items'][0]['id']}",headers=API_HEADERS).status_code == 200
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Alert)) == listing["total"]
        assert db.scalar(select(SourceObservation).where(SourceObservation.job_id==jid)) is not None


def test_alert_dedup_and_change_detection(client, valid_onion_url, db_session_factory):
    sid=enabled(client,valid_onion_url)
    run_text(sid,db_session_factory,"News ransomware leak")
    first=client.get('/api/v1/alerts',headers=API_HEADERS).json()['total']
    assert first >= 1
    run_text(sid,db_session_factory,"News ransomware leak")
    assert client.get('/api/v1/alerts',headers=API_HEADERS).json()['total'] == first
    run_text(sid,db_session_factory,"News ransomware leak about another incident")
    rows=client.get('/api/v1/alerts',headers=API_HEADERS).json()
    assert rows['total'] > first
    assert any(x['event_type']=='CONTENT_CHANGED' for x in rows['items'])
    with db_session_factory() as db:
        obs=db.scalars(select(SourceObservation).order_by(SourceObservation.created_at.desc(),SourceObservation.id.desc())).all()
        for observation in obs:
            assert emit_observation_alerts(db,observation) == 0
        db.commit()


def test_relevance_threshold_one_signal_per_content(client, valid_onion_url, db_session_factory):
    sid=enabled(client,valid_onion_url)
    wid=client.post('/api/v1/watchlists',headers=API_HEADERS,json={'name':'score-test'}).json()['id']
    client.post(f'/api/v1/watchlists/{wid}/rules',headers=API_HEADERS,json={'phrase':'alpha', 'weight':30})
    run_text(sid,db_session_factory,'alpha alpha alpha')
    events=client.get('/api/v1/alerts',headers=API_HEADERS).json()['items']
    assert len([x for x in events if x['event_type']=='RELEVANCE_THRESHOLD']) == 1
    assert any(x['relevance_score']>=RELEVANCE_ALERT_THRESHOLD for x in events)


def test_sensitive_content_produces_only_review_signal(client, valid_onion_url, db_session_factory):
    sid=enabled(client,valid_onion_url)
    run_text(sid,db_session_factory,'news article child sexual abuse material CVE-2025-98765 stolen database')
    events=client.get('/api/v1/alerts',headers=API_HEADERS).json()['items']
    assert len(events)==1 and events[0]['event_type']=='SENSITIVE_REVIEW'
    assert events[0]['signal_code']=='REVIEW_REQUIRED'
    assert events[0]['priority']=='HIGH'
    assert 'child sexual abuse material' not in str(events)


def test_acknowledgement_resolution_and_audit(client, valid_onion_url, db_session_factory):
    sid=enabled(client,valid_onion_url)
    run_text(sid,db_session_factory,'news ransomware leak')
    aid=client.get('/api/v1/alerts',headers=API_HEADERS).json()['items'][0]['id']
    path=f'/api/v1/alerts/{aid}'
    assert client.patch(path, json={'status':'ACKNOWLEDGED'}).status_code == 401
    assert client.patch(path, headers=API_HEADERS, json={'status':'INVALID'}).status_code == 422
    assert client.patch(path, headers=API_HEADERS, json={'status':'ACKNOWLEDGED','reason':'ok'}).status_code == 422
    r=client.patch(path, headers=API_HEADERS, json={'status':'ACKNOWLEDGED'});
    assert r.status_code==200 and r.json()['acknowledged_at']
    assert client.patch(path,headers=API_HEADERS,json={'status':'ACKNOWLEDGED'}).status_code==409
    r=client.patch(path,headers=API_HEADERS,json={'status':'RESOLVED'})
    assert r.status_code==200 and r.json()['resolved_at']
    assert client.patch(path,headers=API_HEADERS,json={'status':'RESOLVED'}).status_code==409
    assert client.get('/api/v1/alerts?status=RESOLVED',headers=API_HEADERS).json()['total']==1
    with db_session_factory() as db:
        audits=db.scalars(select(AuditLog).where(AuditLog.action=='alert.review')).all()
        assert len(audits)==2
        assert all(json.loads(a.details)['reason']=='Manual check' for a in audits)


def test_empty_and_missing_alerts(client):
    assert client.get('/api/v1/alerts',headers=API_HEADERS).json()['total']==0
    assert client.get(f'/api/v1/alerts/{uuid.uuid4()}',headers=API_HEADERS).status_code==404
    assert client.patch(f'/api/v1/alerts/{uuid.uuid4()}',headers=API_HEADERS,
                        json={'status':'ACKNOWLEDGED'}).status_code==404


def test_report_snapshot_json_csv_are_immutable(client, valid_onion_url, db_session_factory):
    sid=enabled(client,valid_onion_url)
    run_text(sid,db_session_factory, 'News ransomware leak CVE-2025-12345')
    request={**period(), 'source_id':sid}
    created=client.post('/api/v1/reports',headers=API_HEADERS,json=request)
    assert created.status_code==201,created.text
    rid=created.json()['id']
    assert client.get(f'/api/v1/reports/{rid}',headers=API_HEADERS).status_code==200
    before=client.get(f'/api/v1/reports/{rid}/export?format=json',headers=API_HEADERS)
    assert before.status_code==200
    assert 'application/json' in before.headers['content-type']
    info=before.json()
    assert info['totals']['observations']==1
    assert info['totals']['alerts']>=1
    assert info['source_id']==sid
    assert info['records']['observations'][0]['verification_status']=='DIRECT_OBSERVATION'
    assert 'ransomware leak' not in before.text
    assert '.onion' not in before.text
    assert 'authorization_note' not in before.text
    csv_response=client.get(f'/api/v1/reports/{rid}/export?format=csv',headers=API_HEADERS)
    assert csv_response.status_code==200
    cells=list(csv.DictReader(io.StringIO(csv_response.text)))
    assert any(row['record_type']=='alerts' for row in cells)
    assert any(row['record_type']=='observations' for row in cells)
    assert 'ransomware leak' not in csv_response.text
    # Subsequent collection changes database, never a persisted snapshot.
    run_text(sid,db_session_factory,'News ransomware leak updated page')
    assert client.get(f'/api/v1/reports/{rid}/export?format=json',headers=API_HEADERS).content == before.content
    assert client.get(f'/api/v1/reports/{rid}/export?format=csv',headers=API_HEADERS).content == csv_response.content
    assert client.get('/api/v1/reports',headers=API_HEADERS).json()['total']==1
    with db_session_factory() as db:
        assert db.get(Report, uuid.UUID(rid)).snapshot['totals']['observations']==1
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='report.create'))==1


def test_reports_bounded_filters_and_access(client, valid_onion_url, db_session_factory):
    sid=enabled(client,valid_onion_url)
    for number in range(4):
        run_text(sid,db_session_factory,f'Public news article number {number}')
    created=client.post('/api/v1/reports',headers=API_HEADERS,
                        json={**period(), 'max_rows_per_type':2, 'source_id':sid})
    assert created.status_code==201
    rid=created.json()['id']
    report=client.get(f'/api/v1/reports/{rid}/export',headers=API_HEADERS).json()
    assert report['totals']['observations']==4
    assert 'observations' in report['truncated_types']
    assert len(report['records']['observations'])==2
    assert client.get('/api/v1/reports?source_id='+sid,headers=API_HEADERS).json()['total']==1
    assert client.get('/api/v1/reports?limit=0',headers=API_HEADERS).status_code==422
    assert client.get(f'/api/v1/reports/{rid}/export?format=xml',headers=API_HEADERS).status_code==422
    assert client.get(f'/api/v1/reports/{uuid.uuid4()}/export',headers=API_HEADERS).status_code==404
    assert client.get(f'/api/v1/reports/{uuid.uuid4()}',headers=API_HEADERS).status_code==404
    assert client.post('/api/v1/reports',headers=API_HEADERS,
                       json={**period(),'source_id':str(uuid.uuid4())}).status_code==404


@pytest.mark.parametrize('modification', [
    {'max_rows_per_type':0}, {'max_rows_per_type':201}, {'extra_field':'invalid'},
    {'period_start':'2026-01-01T00:00:00'},
    {'period_end':'2026-01-01T00:00:00+00:00'},
    {'period_start':'2019-01-01T00:00:00+00:00'},
    {'period_end':'2040-01-01T00:00:00+00:00'},
])
def test_report_invalid_requests(client, modification):
    assert client.post('/api/v1/reports',headers=API_HEADERS,json={**period(),**modification}).status_code==422


def test_empty_report_headers(client):
    r=client.post('/api/v1/reports',headers=API_HEADERS,json=period())
    assert r.status_code==201
    rid=r.json()['id']
    assert client.get(f'/api/v1/reports/{rid}/export?format=json',headers=API_HEADERS).json()['totals']['alerts']==0
    data=client.get(f'/api/v1/reports/{rid}/export?format=csv',headers=API_HEADERS).text
    assert data.startswith('record_type,')
    assert len(data.splitlines())==1


def test_no_retroactive_alert_replay(client, valid_onion_url, db_session_factory):
    sid=enabled(client, valid_onion_url)
    run_text(sid, db_session_factory,'Plain article without any monitored entities')
    assert client.get('/api/v1/alerts',headers=API_HEADERS).json()['total']==0


def test_alert_fingerprint_scoped_by_source(client, valid_onion_url, db_session_factory):
    a=enabled(client,valid_onion_url)
    b=enabled(client,onion(23))
    for sid in (a,b):
        run_text(sid,db_session_factory,'ransomware leak')
    alerts=client.get('/api/v1/alerts',headers=API_HEADERS).json()['items']
    claims=[item for item in alerts if item['signal_code']=='RANSOMWARE_CLAIM']
    assert len(claims)==2 and {x['source_id'] for x in claims}=={a,b}


def test_direct_resolve_and_no_reopen(client, valid_onion_url, db_session_factory):
    sid=enabled(client,valid_onion_url)
    run_text(sid,db_session_factory,'ransomware leak')
    aid=client.get('/api/v1/alerts',headers=API_HEADERS).json()['items'][0]['id']
    assert client.patch(f'/api/v1/alerts/{aid}',headers=API_HEADERS,
                        json={'status':'RESOLVED'}).status_code==200
    assert client.patch(f'/api/v1/alerts/{aid}',headers=API_HEADERS,
                        json={'status':'ACKNOWLEDGED'}).status_code==409


def test_report_excludes_out_of_period_data(client, valid_onion_url, db_session_factory):
    sid=enabled(client,valid_onion_url)
    run_text(sid,db_session_factory,'ransomware leak')
    old=datetime.now(timezone.utc)-timedelta(days=30)
    report=client.post('/api/v1/reports',headers=API_HEADERS,json={
        'source_id':sid,
        'period_start':(old-timedelta(days=1)).isoformat(),
        'period_end':old.isoformat(),
    })
    assert report.status_code==201
    snapshot=client.get(f'/api/v1/reports/{report.json()["id"]}/export',headers=API_HEADERS).json()
    assert all(count==0 for count in snapshot['totals'].values())
