"""M6-B: synthetic, offline analyst-workflow test coverage."""
import uuid

from sqlalchemy import func, select
from app.models import AnalystCase, AnalystCaseNote, AnalystCaseEvent, AuditLog
from tests.test_m6a_cases import LEGACY, alert, create, person, update


def note(client, row, **extra):
    body = {'expected_version': row['version'], 'note_code': 'FOLLOW_UP',
            'body': 'Verify the timeline with a second reviewer.'}
    body.update(extra)
    return client.post(f"/api/v1/cases/{row['id']}/notes", headers=LEGACY, json=body)


def test_priority_is_independent_of_alert_and_audited(client, db_session_factory):
    row = create(client, db_session_factory)
    assert row['priority'] == 'UNASSESSED'
    changed = update(client, row, 'SET_PRIORITY', priority='HIGH')
    assert changed.status_code == 200, changed.text
    current = changed.json()
    assert current['priority'] == 'HIGH' and current['version'] == 2
    assert update(client, row, 'SET_PRIORITY', priority='CRITICAL').status_code == 409
    assert update(client, current, 'SET_PRIORITY', priority='HIGH').status_code == 409
    event = client.get(f"/api/v1/cases/{row['id']}/events", headers=LEGACY).json()['items'][0]
    assert event['action'] == 'SET_PRIORITY' and event['reason_code'] == 'HIGH'
    with db_session_factory() as db:
        from app.models import Alert
        assert db.get(Alert, uuid.UUID(row['alert_id'])).priority == 'LOW'


def test_escalation_requires_reason_and_is_traced(client, db_session_factory):
    row = create(client, db_session_factory)
    row = update(client, row, 'START_REVIEW').json()
    missing = client.patch(f"/api/v1/cases/{row['id']}", headers=LEGACY,
                           json={'action':'ESCALATE','expected_version':row['version']})
    assert missing.status_code == 422
    escalated = update(client, row, 'ESCALATE', escalation_reason='MULTI_SOURCE')
    assert escalated.status_code == 200, escalated.text
    entry = client.get(f"/api/v1/cases/{row['id']}/events", headers=LEGACY).json()['items'][0]
    assert entry['reason_code'] == 'MULTI_SOURCE'
    assert escalated.json()['status'] == 'ESCALATED'


def test_internal_note_versions_are_atomic_and_audit_does_not_copy_body(client, db_session_factory):
    row = create(client, db_session_factory)
    message = 'Follow-up needed for documentary verification.'
    resp = note(client, row, body=message)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created['body'] == message and created['case_version'] == 2
    assert note(client, row).status_code == 409
    listed = client.get(f"/api/v1/cases/{row['id']}/notes", headers=LEGACY).json()
    assert listed['total'] == 1 and listed['items'][0]['actor']
    fetched = client.get(f"/api/v1/cases/{row['id']}", headers=LEGACY).json()
    assert fetched['version'] == 2
    assert update(client, row, 'START_REVIEW').status_code == 409
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AnalystCaseNote)) == 1
        assert db.scalar(select(func.count()).select_from(AnalystCaseEvent)) == 2
        audit = db.scalars(select(AuditLog).where(AuditLog.entity_type == 'analyst_case')).all()
        assert all(message not in item.details for item in audit)
        assert any(item.action == 'case.note' for item in audit)


def test_note_validation_forbidden_content(client, db_session_factory):
    row = create(client, db_session_factory)
    for body in ['   ', '1234567', 'See https://example.org/page',
                 'username@example.org', 'Look at abc.onion location',
                 'The password is demo', 'BearER abcdefghi', 'First\nSecond entry',
                 'x' * 301]:
        response = note(client, row, body=body)
        assert response.status_code == 422, (body, response.text)
    for invalid in [{'note_code':'FREEFORM'}, {'unexpected_excerpt':'raw page'},
                    {'expected_version':0}]:
        assert note(client, row, **invalid).status_code == 422
    assert client.get(f"/api/v1/cases/{row['id']}", headers=LEGACY).json()['version'] == 1


def test_closed_case_is_immutable_and_annotations_remain_readable(client, db_session_factory):
    row = create(client, db_session_factory)
    assert note(client, row).status_code == 201
    row = client.get(f"/api/v1/cases/{row['id']}", headers=LEGACY).json()
    row = update(client, row, 'START_REVIEW').json()
    row = update(client, row, 'CLOSE', closure_code='DOCUMENTED').json()
    assert note(client, row).status_code == 409
    assert update(client, row, 'SET_PRIORITY', priority='HIGH').status_code == 409
    assert client.get(f"/api/v1/cases/{row['id']}/notes", headers=LEGACY).json()['total'] == 1


def test_note_rbac_and_unknown_case(client, db_session_factory):
    row = create(client, db_session_factory)
    viewer = person(db_session_factory, 'case-note-viewer', 'VIEWER')
    for route in ['notes', 'notification-preview']:
        assert client.get(f"/api/v1/cases/{row['id']}/{route}", headers=viewer).status_code == 403
    assert client.post(f"/api/v1/cases/{row['id']}/notes", headers=viewer,
                       json={'expected_version':1,'note_code':'FOLLOW_UP','body':'The second reviewer will check.'}).status_code == 403
    missing = str(uuid.uuid4())
    assert client.get(f'/api/v1/cases/{missing}/notes',headers=LEGACY).status_code == 404
    assert note(client, {'id':missing,'version':1}).status_code == 404


def test_notification_preview_is_non_dispatching_and_minimal(client, db_session_factory):
    row = create(client, db_session_factory)
    resp = client.get(f"/api/v1/cases/{row['id']}/notification-preview", headers=LEGACY)
    assert resp.status_code == 200
    value = resp.json()
    assert value['delivery'] == 'DISABLED' and value['enabled'] is False
    assert value['destinations'] == [] and value['contents'] == 'METADATA_ONLY'
    assert not any(x in str(value).lower() for x in ('webhook', 'email', 'secret', 'observation_body'))


def test_pagination_notes(client, db_session_factory):
    row = create(client, db_session_factory)
    for i in range(3):
        assert note(client, row, body=f'Synthetic note number {i} to document review.').status_code == 201
        row = client.get(f"/api/v1/cases/{row['id']}", headers=LEGACY).json()
    page = client.get(f"/api/v1/cases/{row['id']}/notes?limit=2&offset=1", headers=LEGACY).json()
    assert page['total'] == 3 and len(page['items']) == 2
    assert page['items'][0]['case_version'] > page['items'][1]['case_version']
