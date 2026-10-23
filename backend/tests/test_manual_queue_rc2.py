"""No live Tor calls. Manual per-source queue, RBAC, workers and regression."""
import asyncio
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.collector.transport import Fetched
from app.collector.worker import claim_one, fail_claimed, process_one
from app.models import AuditLog, CrawlJob, SourceObservation
from app.security.api_key import fingerprint, new_token
from app.models.identity import Operator, OperatorToken

LEGACY = {"X-API-Key": "local-test-only-api-key-strong-and-unique"}
REASON = {"reason": "Manual check"}


def registered(client, valid_onion_url):
    created = client.post('/api/v1/sources', headers=LEGACY, json={
        'url': valid_onion_url, 'name': 'Local synthetic authorized source',
        'authorization_confirmed': True, 'authorization_note': 'Manual approval',
    })
    assert created.status_code == 201, created.text
    return created.json()['id']


def enable(client, sid):
    res = client.post(f'/api/v1/sources/{sid}/collection/enable', headers=LEGACY, json=REASON)
    assert res.status_code == 200


def create_role(factory, role):
    token = new_token()
    with factory() as db:
        op = Operator(username='queue-' + role.lower(), role=role, active=True)
        db.add(op)
        db.flush()
        from datetime import timedelta
        db.add(OperatorToken(operator_id=op.id, token_hash=fingerprint(token),
                             expires_at=datetime.now(timezone.utc) + timedelta(days=3)))
        db.commit()
    return {'X-API-Key': token}


def test_manual_queue_permissions_and_source_approval(client, db_session_factory, valid_onion_url):
    sid = registered(client, valid_onion_url)
    viewer = create_role(db_session_factory, 'VIEWER')
    analyst = create_role(db_session_factory, 'ANALYST')
    path = f'/api/v1/sources/{sid}/collection/run'
    assert client.post(path, json=REASON).status_code == 401
    assert client.post(path, headers=viewer, json=REASON).status_code == 403
    assert client.post(path, headers=analyst, json=REASON).status_code == 409
    enable(client, sid)
    assert client.post(path, headers=analyst, json={'reason': 'short'}).status_code == 422
    res = client.post(path, headers=analyst, json=REASON)
    assert res.status_code == 202, res.text
    assert res.json()['status'] == 'PENDING'
    assert res.json()['started_at'] is None
    assert client.post(path, headers=analyst, json=REASON).status_code == 409
    jobs = client.get('/api/v1/collection/jobs?source_id='+sid, headers=viewer)
    assert jobs.status_code == 200
    assert jobs.json()['total'] == 1
    latest = client.get('/api/v1/collection/latest?source_ids='+sid, headers=viewer)
    assert latest.status_code == 200 and latest.json()[0]['id'] == res.json()['id']
    with db_session_factory() as db:
        log = db.scalar(select(AuditLog).where(AuditLog.action == 'collection.enqueue'))
        assert log is not None and log.actor == 'queue-analyst'
        assert json.loads(log.details)['reason'] == 'Manual check'


def test_worker_claim_and_one_http_root_only(client, db_session_factory, valid_onion_url):
    sid = registered(client, valid_onion_url)
    enable(client, sid)
    queued = client.post(f'/api/v1/sources/{sid}/collection/run', headers=LEGACY, json=REASON)
    assert queued.status_code == 202
    seen = []
    async def fake_fetch(url):
        seen.append(url)
        return Fetched(200,'text/html','utf-8',b'<html><title>Synthetic</title><body>Approved text</body></html>')
    assert asyncio.run(process_one(db_session_factory, fetcher=fake_fetch))
    assert seen == [valid_onion_url]
    latest = client.get('/api/v1/collection/latest?source_ids='+sid, headers=LEGACY).json()
    assert latest[0]['status'] == 'COMPLETED'
    assert latest[0]['id'] == queued.json()['id']
    assert latest[0]['finished_at'] is not None
    with db_session_factory() as db:
        observation = db.scalar(select(SourceObservation))
        assert observation is not None
        assert str(observation.job_id) == queued.json()['id']
    assert asyncio.run(process_one(db_session_factory, fetcher=fake_fetch)) is False
    assert len(seen) == 1
    # A later explicit click is allowed and creates a distinct one-shot job.
    assert client.post(f'/api/v1/sources/{sid}/collection/run', headers=LEGACY, json=REASON).status_code == 202


@pytest.mark.parametrize('action', ['revoke', 'deactivate', 'collection/disable'])
def test_revocation_after_enqueue_prevents_any_fetch(client, db_session_factory, valid_onion_url, action):
    sid = registered(client, valid_onion_url)
    enable(client, sid)
    resp = client.post(f'/api/v1/sources/{sid}/collection/run', headers=LEGACY, json=REASON)
    assert resp.status_code == 202
    client.post(f'/api/v1/sources/{sid}/{action}', headers=LEGACY, json=REASON)
    called=[]
    async def forbidden_fetch(url):
        called.append(url)
        raise AssertionError('Tor must never be contacted')
    assert asyncio.run(process_one(db_session_factory, fetcher=forbidden_fetch)) is False
    assert called == []
    job = client.get(f'/api/v1/collection/jobs/{resp.json()["id"]}', headers=LEGACY).json()
    assert job['status'] == 'FAILED' and job['error_code'] == 'AUTHORIZATION_REVOKED'


def test_worker_network_error_generic_failure(client, db_session_factory, valid_onion_url):
    sid = registered(client, valid_onion_url)
    enable(client, sid)
    client.post(f'/api/v1/sources/{sid}/collection/run', headers=LEGACY, json=REASON)
    from app.collector.transport import CollectError
    async def err(url): raise CollectError('TOR_NETWORK_ERROR')
    assert asyncio.run(process_one(db_session_factory, fetcher=err))
    job = client.get('/api/v1/collection/latest?source_ids='+sid, headers=LEGACY).json()[0]
    assert job['status']=='FAILED' and job['error_code']=='TOR_NETWORK_ERROR'


def test_partial_unique_index_denies_second_active_job(db_session_factory, client, valid_onion_url):
    sid = registered(client, valid_onion_url)
    enable(client, sid)
    with db_session_factory() as db:
        import uuid
        db.add(CrawlJob(source_id=uuid.UUID(sid), status='PENDING'))
        db.commit()
    with pytest.raises(IntegrityError):
        with db_session_factory() as db:
            import uuid
            db.add(CrawlJob(source_id=uuid.UUID(sid), status='RUNNING'))
            db.commit()


def test_worker_crash_generic_failed_job(db_session_factory, client, valid_onion_url):
    sid=registered(client,valid_onion_url)
    enable(client,sid)
    res=client.post(f'/api/v1/sources/{sid}/collection/run',headers=LEGACY,json=REASON)
    claimed=claim_one(db_session_factory)
    assert str(claimed[0])==res.json()['id']
    fail_claimed(db_session_factory, claimed[0])
    job=client.get('/api/v1/collection/latest?source_ids='+sid,headers=LEGACY).json()[0]
    assert job['status']=='FAILED' and job['error_code']=='COLLECTION_FAILED'


def test_latest_jobs_one_per_source(client, db_session_factory, valid_onion_url):
    from app.models import OnionSource
    from uuid import UUID
    first = registered(client, valid_onion_url)
    enable(client, first)
    r = client.post(f'/api/v1/sources/{first}/collection/run', headers=LEGACY, json=REASON)
    with db_session_factory() as db:
        source = db.get(OnionSource, UUID(first))
        # Reuse one previously queued source and ensure the projection is bounded.
        job = db.get(CrawlJob, UUID(r.json()['id']))
        job.status='COMPLETED'
        db.add(CrawlJob(source_id=source.id, status='PENDING'))
        db.commit()
    page = client.get(f'/api/v1/collection/latest?source_ids={first}', headers=LEGACY)
    assert page.status_code==200 and len(page.json())==1
    assert page.json()[0]['status'] in ('PENDING','COMPLETED')
    assert client.get('/api/v1/collection/latest', headers=LEGACY).json()==[]


def test_migration_from_rc1_creates_duplicate_job_guard(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    from sqlalchemy import create_engine, text
    root = Path(__file__).resolve().parents[1]
    url=f'sqlite+pysqlite:///{tmp_path / "legacy.sqlite"}'
    for revision in ('0007_named_access','head'):
        result=subprocess.run([sys.executable,'-m','alembic','upgrade',revision],cwd=root,
                              env={**os.environ,'OIP_DATABASE_URL':url},capture_output=True,text=True,timeout=60)
        assert result.returncode==0,result.stdout+result.stderr
    engine=create_engine(url)
    with engine.begin() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version'))=='0008_manual_queue'
        statement=db.scalar(text("SELECT sql FROM sqlite_master WHERE name='uq_crawl_jobs_active_source'"))
        assert statement and 'UNIQUE INDEX' in statement
    engine.dispose()


def test_recover_stale_only_closes_old_running_jobs(client, db_session_factory, valid_onion_url):
    from app.collector.worker import recover_stale
    from uuid import UUID
    from datetime import timedelta
    sid=registered(client,valid_onion_url)
    enable(client,sid)
    queued=client.post(f'/api/v1/sources/{sid}/collection/run',headers=LEGACY,json=REASON).json()['id']
    assert claim_one(db_session_factory)[0]==UUID(queued)
    assert recover_stale(db_session_factory)==0
    with db_session_factory() as db:
        job=db.get(CrawlJob,UUID(queued))
        job.started_at=datetime.now(timezone.utc)-timedelta(hours=2)
        db.commit()
    assert recover_stale(db_session_factory)==1
    assert recover_stale(db_session_factory)==0
    job=client.get(f'/api/v1/collection/jobs/{queued}',headers=LEGACY).json()
    assert job['status']=='FAILED' and job['error_code']=='WORKER_INTERRUPTED'
