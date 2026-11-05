"""Visitor boundary: synthetic data only, no network, no collection."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from tests.route_inventory import api_routes
from sqlalchemy import select

from app.main import app
from app.models import (AuditLog, ClassificationResult, CrawlJob, OnionSource,
                        Operator, OperatorToken, Report, ReportPublication, SourceObservation)
from app.security.api_key import fingerprint, new_token

ADMIN = {'X-API-Key': 'local-test-only-api-key-strong-and-unique'}
COUNTERS = dict(observations=3, discoveries=2, classifications=1, indicators=4, alerts=0)
SENTINEL = 'INTERNAL_PRIVATE_SENTINEL'


def seed(factory, url, *, name='Source de démonstration', status='COMPLETED', protected=False):
    with factory() as db:
        source = OnionSource(name=name, canonical_url=url, authorization_note=SENTINEL,
                             description=SENTINEL, collection_enabled=True)
        db.add(source); db.flush()
        job = CrawlJob(source_id=source.id, status=status, error_code=SENTINEL,
                       lease_token=uuid.uuid4(), finished_at=datetime.now(timezone.utc))
        db.add(job); db.flush()
        obs = SourceObservation(source_id=source.id, job_id=job.id, http_status=200,
                                content_type='text/html', response_bytes=1234, text_length=42,
                                title=SENTINEL, description=SENTINEL, text_sha256='c'*64)
        db.add(obs); db.flush()
        if protected:
            db.add(ClassificationResult(source_id=source.id, observation_id=obs.id,
                category='SUSPECTED_CHILD_EXPLOITATION', confidence=90, evidence_codes=[],
                ruleset_version='TEST', review_status='REVIEW_REQUIRED'))
        report = Report(source_id=source.id, period_start=datetime.now(timezone.utc)-timedelta(days=1),
                        period_end=datetime.now(timezone.utc),
                        snapshot={'totals': {**COUNTERS, 'secret': SENTINEL},
                                  'records': {'observations': [{'title': SENTINEL, 'url': url}]},
                                  'disclaimer': SENTINEL, 'source_id': str(source.id)})
        db.add(report); db.commit()
        return source.id, job.id, obs.id, report.id


def test_public_api_has_exact_read_only_allowlist():
    paths = {r.path: r.methods for r in api_routes(app) if r.path.startswith('/api/public/')}
    assert paths == {'/api/public/v1/activity': {'GET'}, '/api/public/v1/reports': {'GET'},
                     '/api/public/v1/reports/{publication_id}': {'GET'}}


def test_anonymous_activity_is_projected_not_serialized(client, db_session_factory, valid_onion_url):
    ids = seed(db_session_factory, valid_onion_url)
    r = client.get('/api/public/v1/activity')
    assert r.status_code == 200 and r.headers['cache-control'] == 'no-store'
    row = r.json()['items'][0]
    assert set(row) == {'date','source_name','status','response_bytes','text_characters'}
    assert row['source_name'] == 'Source de démonstration'
    assert row['status'] == 'COMPLETED' and row['response_bytes'] == 1234 and row['text_characters'] == 42
    for private in [SENTINEL, valid_onion_url, *map(str, ids), 'c'*64]:
        assert private not in r.text


@pytest.mark.parametrize('name', ['http://private.onion/', 'hidden.onion', 'email@example.test',
                                  'oip_SYNTHETIC_TOKEN', 'name\nprivate', 'secret=hidden'])
def test_unsafe_source_labels_are_not_public(client, db_session_factory, valid_onion_url, name):
    seed(db_session_factory, valid_onion_url, name=name)
    r=client.get('/api/public/v1/activity')
    assert r.json()['items'][0]['source_name'] == 'Source (nom masqué)'
    assert name not in r.text


@pytest.mark.parametrize('change', ['protected','deleted','inactive','unapproved','pending'])
def test_restricted_or_unfinished_sources_are_not_listed(client, db_session_factory, valid_onion_url, change):
    source_id, job_id, _, _=seed(db_session_factory, valid_onion_url,
                               protected=change=='protected',status='PENDING' if change=='pending' else 'COMPLETED')
    with db_session_factory() as db:
        source=db.get(OnionSource,source_id)
        if change=='deleted':source.deleted_at=datetime.now(timezone.utc)
        if change=='inactive':source.is_active=False
        if change=='unapproved':source.approved_for_collection=False
        db.commit()
    assert client.get('/api/public/v1/activity').json()['total']==0


def test_failed_job_does_not_expose_error_or_observation_volumes(client, db_session_factory, valid_onion_url):
    seed(db_session_factory, valid_onion_url,status='FAILED')
    row=client.get('/api/public/v1/activity').json()['items'][0]
    assert row['status']=='FAILED' and row['response_bytes'] is None and row['text_characters'] is None


@pytest.mark.parametrize('path', ['/api/public/v1/activity?limit=51', '/api/public/v1/activity?offset=10001',
                                   '/api/public/v1/reports?limit=0','/api/public/v1/reports?offset=-1'])
def test_public_pagination_is_bounded(client,path):
    assert client.get(path).status_code==422


def test_internal_reads_and_writes_stay_protected(client, db_session_factory, valid_onion_url):
    *_, report_id=seed(db_session_factory,valid_onion_url)
    for path in ['/api/v1/sources','/api/v1/collection/jobs','/api/v1/observations/search',
                 '/api/v1/reports',f'/api/v1/reports/{report_id}',
                 f'/api/v1/reports/{report_id}/export',f'/api/v1/reports/{report_id}/publication-preview',
                 '/api/v1/auth/me','/api/v1/cases']:
        assert client.get(path).status_code==401,path
    assert client.post(f'/api/v1/reports/{report_id}/publication',json={}).status_code==401
    for role in ['VIEWER','ANALYST']:
        token=new_token()
        with db_session_factory() as db:
            op=Operator(username='visitor_'+role,role=role);db.add(op);db.flush()
            db.add(OperatorToken(operator_id=op.id,token_hash=fingerprint(token),
                                 expires_at=datetime.now(timezone.utc)+timedelta(days=1)));db.commit()
        headers={'X-API-Key':token}
        assert client.get(f'/api/v1/reports/{report_id}/publication-preview',headers=headers).status_code==403
        assert client.post(f'/api/v1/reports/{report_id}/publication',headers=headers,json={}).status_code==403
        assert client.delete(f'/api/v1/reports/{report_id}/publication/{uuid.uuid4()}',headers=headers).status_code==403


def test_explicit_publication_snapshot_and_withdrawal(client,db_session_factory,valid_onion_url):
    ids=seed(db_session_factory,valid_onion_url); report_id=ids[-1]
    base=f'/api/v1/reports/{report_id}'
    assert client.get('/api/public/v1/reports').json()['total']==0
    assert client.get(f'/api/public/v1/reports/{report_id}').status_code==404
    preview=client.get(base+'/publication-preview',headers=ADMIN).json()
    assert preview['content']['totals']==COUNTERS
    assert SENTINEL not in str(preview) and valid_onion_url not in str(preview)
    assert client.post(base+'/publication',headers=ADMIN,json={'expected_digest':'0'*64}).status_code==409
    response=client.post(base+'/publication',headers=ADMIN,json={'expected_digest':preview['digest']})
    assert response.status_code==201,response.text
    public_id=response.json()['publication_id']
    assert public_id!=str(report_id)
    assert client.post(base+'/publication',headers=ADMIN,json={'expected_digest':preview['digest']}).status_code==409
    published=client.get('/api/public/v1/reports/'+public_id)
    assert published.status_code==200 and published.json()['content']==preview['content']
    assert set(published.json())=={'id','published_at','content'}
    for private in [SENTINEL,valid_onion_url,*map(str,ids)]:assert private not in published.text
    with db_session_factory() as db:
        row=db.get(Report,report_id);row.snapshot={'totals':dict(COUNTERS,observations=999)};db.commit()
    assert client.get('/api/public/v1/reports/'+public_id).json()['content']['totals']==COUNTERS
    assert client.delete(base+'/publication/'+public_id,headers=ADMIN).status_code==204
    assert client.get('/api/public/v1/reports/'+public_id).status_code==404
    assert client.get('/api/public/v1/reports').json()['total']==0
    assert client.get(base,headers=ADMIN).status_code==200
    with db_session_factory() as db:
        assert db.scalar(select(ReportPublication)).is_public is False
        actions=list(db.scalars(select(AuditLog.action)))
        assert actions.count('report.publish')==1 and actions.count('report.unpublish')==1
    # Republish gets a new public version; stale withdrawals cannot remove it.
    preview=client.get(base+'/publication-preview',headers=ADMIN).json()
    new=client.post(base+'/publication',headers=ADMIN,json={'expected_digest':preview['digest']}).json()['publication_id']
    assert new!=public_id
    assert client.delete(base+'/publication/'+public_id,headers=ADMIN).status_code==404
    assert client.get('/api/public/v1/reports/'+new).status_code==200


def test_malformed_counter_is_blocked_without_reflecting_it(client,db_session_factory,valid_onion_url):
    *_, report_id=seed(db_session_factory,valid_onion_url)
    with db_session_factory() as db:
        db.get(Report,report_id).snapshot={'totals':dict(COUNTERS,observations=SENTINEL)};db.commit()
    r=client.get(f'/api/v1/reports/{report_id}/publication-preview',headers=ADMIN)
    assert r.status_code==409 and SENTINEL not in r.text
