"""M6-A cases are manual metadata records; all data and credentials synthetic."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import (Alert, AnalystCase, AnalystCaseEvent, AuditLog, CrawlJob,
                        OnionSource, Operator, OperatorToken, SourceObservation)
from app.security.api_key import fingerprint, new_token

LEGACY = {"X-API-Key": "local-test-only-api-key-strong-and-unique"}


def person(factory, name, role="ANALYST", active=True):
    key = new_token()
    with factory() as db:
        op = Operator(username=name, role=role, active=active)
        db.add(op)
        db.flush()
        db.add(OperatorToken(operator_id=op.id, token_hash=fingerprint(key),
                             expires_at=datetime.now(timezone.utc) + timedelta(days=2)))
        db.commit()
    return {"X-API-Key": key}


def alert(factory, key=None):
    key = key or uuid.uuid4().hex[:12]
    with factory() as db:
        source = OnionSource(canonical_url=f'http://m6-synthetic-{key}.onion/', name='Synthetic',
                             authorization_note='Test fixture only')
        db.add(source)
        db.flush()
        job = CrawlJob(source_id=source.id, status='COMPLETED')
        db.add(job)
        db.flush()
        observation = SourceObservation(job_id=job.id, source_id=source.id, http_status=200,
                                        content_type='text/plain', response_bytes=10,
                                        text_sha256='f'*64, text_length=10)
        db.add(observation)
        db.flush()
        row = Alert(source_id=source.id, observation_id=observation.id, fingerprint=uuid.uuid4().hex,
                    event_type='DOCUMENTARY_SIGNAL', signal_code='SYNTHETIC', priority='LOW',
                    verification_status='UNVERIFIED', relevance_score=10)
        db.add(row)
        db.commit()
        return str(row.id)


def create(client, factory, headers=LEGACY):
    resp = client.post('/api/v1/cases', headers=headers, json={'alert_id':alert(factory)})
    assert resp.status_code == 201, resp.text
    return resp.json()


def update(client, row, action, *, headers=LEGACY, **params):
    if action == 'ESCALATE' and 'escalation_reason' not in params:
        params['escalation_reason'] = 'REVIEW_REQUIRED'
    return client.patch(f"/api/v1/cases/{row['id']}", headers=headers,
                        json={'action': action, 'expected_version': row['version'], **params})


def test_create_requires_alert_and_no_duplicates(client, db_session_factory):
    assert client.post('/api/v1/cases', json={'alert_id':str(uuid.uuid4())}).status_code == 401
    assert client.post('/api/v1/cases', headers=LEGACY, json={'alert_id':str(uuid.uuid4())}).status_code == 404
    row = create(client, db_session_factory)
    assert row['status'] == 'OPEN' and row['version'] == 1 and row['assignee_id'] is None
    assert client.post('/api/v1/cases', headers=LEGACY, json={'alert_id':row['alert_id']}).status_code == 409
    response = client.get(f"/api/v1/cases/{row['id']}", headers=LEGACY)
    assert response.status_code == 200 and response.json()['id'] == row['id']
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AnalystCase)) == 1
        assert db.scalar(select(func.count()).select_from(AnalystCaseEvent)) == 1


def test_rbac_viewer_refused_on_all_routes(client, db_session_factory):
    viewer = person(db_session_factory, 'observer', 'VIEWER')
    row = create(client, db_session_factory)
    for path in ['/api/v1/cases', '/api/v1/cases/assignees', f"/api/v1/cases/{row['id']}",
                 f"/api/v1/cases/{row['id']}/events"]:
        assert client.get(path, headers=viewer).status_code == 403
    assert client.post('/api/v1/cases', headers=viewer, json={'alert_id':row['alert_id']}).status_code == 403
    assert update(client,row,'START_REVIEW',headers=viewer).status_code == 403


def test_named_assignment_and_unassignment(client, db_session_factory):
    analyst = person(db_session_factory,'reviewer')
    person(db_session_factory,'inactive','ADMIN',active=False)
    person(db_session_factory,'viewer','VIEWER')
    row = create(client, db_session_factory)
    for who in ['inactive','viewer','missing']:
        assert update(client,row,'ASSIGN',assignee_username=who).status_code == 422
    assert client.get('/api/v1/cases/assignees',headers=analyst).json() == [{'username':'reviewer','role':'ANALYST'}]
    resp = update(client,row,'ASSIGN',headers=analyst,assignee_username='reviewer')
    assert resp.status_code == 200, resp.text
    row = resp.json()
    assert row['assignee_username'] == 'reviewer' and row['version'] == 2
    assert update(client,row,'ASSIGN',assignee_username='reviewer').status_code == 409
    unassigned = update(client,row,'UNASSIGN')
    assert unassigned.status_code == 200 and unassigned.json()['assignee_username'] is None
    assert client.get('/api/v1/cases?assignee_username=reviewer',headers=LEGACY).json()['total'] == 0


def test_version_conflicts_are_atomic_and_history_preserved(client, db_session_factory):
    row = create(client, db_session_factory)
    moved = update(client,row,'START_REVIEW')
    assert moved.status_code == 200
    assert update(client,row,'START_REVIEW').status_code == 409
    changed = moved.json()
    assert changed['version'] == 2 and changed['status'] == 'IN_REVIEW'
    history = client.get(f"/api/v1/cases/{row['id']}/events", headers=LEGACY).json()
    assert [e['version'] for e in history['items']] == [2,1]
    assert history['total'] == 2
    assert history['items'][0]['action'] == 'START_REVIEW'
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AnalystCaseEvent)) == 2


def test_valid_lifecycle_and_closed_immutable(client, db_session_factory):
    row = create(client,db_session_factory)
    row = update(client,row,'START_REVIEW').json()
    row = update(client,row,'ESCALATE').json()
    assert row['status'] == 'ESCALATED'
    row = update(client,row,'RETURN_REVIEW').json()
    row = update(client,row,'ESCALATE').json()
    done = update(client,row,'CLOSE',closure_code='DOCUMENTED')
    assert done.status_code == 200, done.text
    assert done.json()['status'] == 'CLOSED' and done.json()['closed_at'] and done.json()['closure_code'] == 'DOCUMENTED'
    assert update(client,done.json(),'ASSIGN',assignee_username='nope').status_code == 409
    with db_session_factory() as db:
        original = db.get(Alert,uuid.UUID(row['alert_id']))
        assert original.status == 'OPEN'   # workflow never asserts real-world remediation


def test_invalid_transitions_and_body_rejection(client, db_session_factory):
    row = create(client,db_session_factory)
    for action in ['ESCALATE','RETURN_REVIEW','CLOSE']:
        args = {'closure_code':'DOCUMENTED'} if action=='CLOSE' else {}
        assert update(client,row,action,**args).status_code == 409
    for data in [
        {'action':'ASSIGN'}, {'action':'START_REVIEW','assignee_username':'reviewer'},
        {'action':'CLOSE'}, {'action':'ASSIGN','assignee_username':'x y'},
        {'action':'START_REVIEW','closure_code':'DOCUMENTED'},
        {'action':'CLOSE','closure_code':'VERIFIED_COMPROMISE'},
        {'action':'START_REVIEW','arbitrary_excerpt':'page body'},
    ]:
        assert client.patch(f"/api/v1/cases/{row['id']}",headers=LEGACY,
                            json={'expected_version':row['version'],**data}).status_code == 422
    assert client.get('/api/v1/cases?status=NOT_REAL',headers=LEGACY).status_code == 422


def test_filter_pagination_and_no_page_content_in_audit(client, db_session_factory):
    first = create(client,db_session_factory)
    second = create(client,db_session_factory)
    started = update(client, first, 'START_REVIEW').json()
    page = client.get('/api/v1/cases?status=IN_REVIEW&limit=1',headers=LEGACY).json()
    assert page['total'] == 1 and page['items'][0]['id'] == started['id']
    all_rows = client.get('/api/v1/cases?limit=1&offset=1',headers=LEGACY).json()
    assert all_rows['total'] == 2 and len(all_rows['items']) == 1
    history = client.get(f"/api/v1/cases/{second['id']}/events?limit=1",headers=LEGACY).json()
    assert history['total'] == 1
    with db_session_factory() as db:
        rows = db.scalars(select(AuditLog).where(AuditLog.entity_type=='analyst_case')).all()
        assert len(rows) == 3
        assert all('body' not in x.details and 'token' not in x.details for x in rows)


def test_unknown_case_and_event_returns_404(client):
    bad = str(uuid.uuid4())
    assert client.get('/api/v1/cases/'+bad,headers=LEGACY).status_code == 404
    assert client.get('/api/v1/cases/'+bad+'/events',headers=LEGACY).status_code == 404
    assert client.patch('/api/v1/cases/'+bad,headers=LEGACY,
                        json={'expected_version':1,'action':'START_REVIEW'}).status_code == 404
