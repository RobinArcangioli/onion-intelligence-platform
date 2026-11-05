"""M6-C: entirely offline, synthetic, no external delivery."""
import uuid
from sqlalchemy import func, select

from app.models import AnalystCaseNote, AuditLog, CaseNotificationDraft, CaseNotificationPolicy
from tests.test_m6a_cases import LEGACY, create, person, update
from tests.test_m6b_case_collaboration import note

PREFIX = '/api/v1/case-operations'


def policy(client, **data):
    payload = {"code": "CASE_REVIEW_V1", "target_status": "ESCALATED", "minimum_priority": "HIGH"}
    payload.update(data)
    return client.post(f'{PREFIX}/policies', headers=LEGACY, json=payload)


def approved(client, row):
    r = client.patch(f"{PREFIX}/policies/{row['id']}", headers=LEGACY,
                     json={"expected_version": row['version'], "approved": True, "enabled": True})
    assert r.status_code == 200, r.text
    return r.json()


def escalated_case(client, factory):
    row = create(client, factory)
    row = update(client, row, 'SET_PRIORITY', priority='HIGH').json()
    row = update(client, row, 'START_REVIEW').json()
    return update(client, row, 'ESCALATE', escalation_reason='REVIEW_REQUIRED').json()


def prepare(client, case, rule, **data):
    payload = {"case_id":case['id'], "expected_case_version":case['version'], "policy_id":rule['id']}
    payload.update(data)
    return client.post(f'{PREFIX}/drafts', headers=LEGACY, json=payload)


def test_default_disabled_no_external_configuration(client, db_session_factory):
    row = policy(client)
    assert row.status_code == 201, row.text
    value = row.json()
    assert not value['enabled'] and not value['approved'] and value['transport'] == 'NONE'
    assert policy(client).status_code == 409
    case = escalated_case(client, db_session_factory)
    assert prepare(client, case, value).status_code == 409
    assert client.get(f'{PREFIX}/drafts', headers=LEGACY).json()['total'] == 0


def test_explicit_approval_and_strict_version(client, db_session_factory):
    value = policy(client).json()
    endpoint = f"{PREFIX}/policies/{value['id']}"
    assert client.patch(endpoint, headers=LEGACY, json={"expected_version":1, "approved":False, "enabled":True}).status_code == 422
    assert client.patch(endpoint, headers=LEGACY, json={"expected_version":99, "approved":True, "enabled":True}).status_code == 409
    value2 = approved(client, value)
    assert value2['version'] == 2 and value2['enabled'] and value2['approved']
    assert client.patch(endpoint, headers=LEGACY, json={"expected_version":1, "approved":False, "enabled":False}).status_code == 409
    disabled = client.patch(endpoint, headers=LEGACY, json={"expected_version":2, "approved":False, "enabled":False})
    assert disabled.status_code == 200 and not disabled.json()['enabled']


def test_only_matching_approved_policy_prepares_local_draft(client, db_session_factory):
    rule = approved(client, policy(client).json())
    row = escalated_case(client, db_session_factory)
    assert prepare(client, row, rule, expected_case_version=1).status_code == 409
    response = prepare(client, row, rule)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data['delivery_status'] == 'NOT_SENT' and data['destinations'] == []
    assert data['payload'] == {"template": "CASE_STATUS_METADATA_V1", "case_id": row['id'],
                                "status": "ESCALATED", "priority": "HIGH", "version": row['version'],
                                "policy_code": "CASE_REVIEW_V1", "content": "METADATA_ONLY"}
    assert prepare(client, row, rule).status_code == 409
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(CaseNotificationDraft)) == 1
        audits = db.scalars(select(AuditLog).where(AuditLog.entity_type == "case_notification")).all()
        assert any(log.action == 'case_notification.draft_prepared' for log in audits)


def test_unmatched_status_and_priority_cannot_prepare(client, db_session_factory):
    rule = approved(client, policy(client).json())
    first = create(client, db_session_factory)
    assert prepare(client, first, rule).status_code == 409
    first = update(client, first, 'START_REVIEW').json()
    first = update(client, first, 'ESCALATE', escalation_reason='REVIEW_REQUIRED').json()
    assert prepare(client, first, rule).status_code == 409
    second = escalated_case(client, db_session_factory)
    rule_disabled = client.patch(f"{PREFIX}/policies/{rule['id']}", headers=LEGACY,
                                 json={"expected_version":rule['version'], "approved":False,"enabled":False}).json()
    assert not rule_disabled['approved']
    assert prepare(client, second, rule_disabled).status_code == 409


def test_snapshot_does_not_include_case_notes_or_sensitive_identifiers(client, db_session_factory):
    case = create(client, db_session_factory)
    assert note(client, case, body='Follow-up required for documentary review.').status_code == 201
    case = client.get(f"/api/v1/cases/{case['id']}", headers=LEGACY).json()
    case = update(client, case, 'SET_PRIORITY', priority='HIGH').json()
    case = update(client, case, 'START_REVIEW').json()
    case = update(client, case, 'ESCALATE', escalation_reason='REVIEW_REQUIRED').json()
    rule = approved(client, policy(client).json())
    payload = prepare(client, case, rule).json()
    assert 'Follow-up required' not in str(payload)
    assert case['alert_id'] not in str(payload)
    assert 'destination' not in str(payload['payload'])
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AnalystCaseNote)) == 1


def test_permissions_and_payload_hardening(client, db_session_factory):
    viewer = person(db_session_factory, 'm6c-viewer', 'VIEWER')
    analyst = person(db_session_factory, 'm6c-analyst', 'ANALYST')
    row = policy(client).json()
    for path in (f'{PREFIX}/policies', f'{PREFIX}/drafts', f'{PREFIX}/summary', f'{PREFIX}/summary/export'):
        assert client.get(path, headers=viewer).status_code == 403
        assert client.get(path).status_code == 401
    assert client.post(f'{PREFIX}/policies', headers=analyst,
                       json={"code":"NEW_RULE","target_status":"CLOSED","minimum_priority":"HIGH"}).status_code == 403
    assert client.patch(f"{PREFIX}/policies/{row['id']}", headers=analyst,
                        json={"expected_version":1,"approved":True,"enabled":True}).status_code == 403
    for bad in ({"code":"bad code"}, {"code":"BAD","target_status":"UNKNOWN"},
                {"code":"NEW","destination":"https://example.org/"}):
        assert policy(client, **bad).status_code == 422
    assert client.post(f'{PREFIX}/drafts', headers=analyst,
                       json={"case_id":str(uuid.uuid4()), "policy_id":str(uuid.uuid4()),
                             "expected_case_version":1, "webhook_url":"http://fixture"}).status_code == 422
    assert len(client.get(f'{PREFIX}/policies', headers=analyst).json()) == 1


def test_operational_summary_export_contains_only_counts(client, db_session_factory):
    case = escalated_case(client, db_session_factory)
    summary = client.get(f'{PREFIX}/summary', headers=LEGACY)
    assert summary.status_code == 200
    data = summary.json()
    assert data['total_cases'] == 1 and data['by_status']['ESCALATED'] == 1
    assert data['by_priority']['HIGH'] == 1 and data['open_unassigned'] == 1
    assert data['notification_drafts'] == 0 and data['notifications_sent'] == 0
    assert data['external_transport'] == 'NOT_IMPLEMENTED'
    csvresp = client.get(f'{PREFIX}/summary/export?format=csv', headers=LEGACY)
    assert csvresp.status_code == 200 and 'by_status,ESCALATED,1' in csvresp.text
    assert case['id'] not in csvresp.text and case['alert_id'] not in csvresp.text
    assert csvresp.headers['Cache-Control'] == 'no-store'
    assert client.get(f'{PREFIX}/summary/export?format=xlsx', headers=LEGACY).status_code == 422


def test_drafts_paginated_and_no_destruction(client, db_session_factory):
    rule = approved(client, policy(client).json())
    for _ in range(3):
        row = escalated_case(client, db_session_factory)
        assert prepare(client, row, rule).status_code == 201
    page = client.get(f'{PREFIX}/drafts?limit=2&offset=1', headers=LEGACY).json()
    assert page['total'] == 3 and len(page['items']) == 2
    assert all(item['delivery_status'] == 'NOT_SENT' for item in page['items'])
    assert client.get(f'{PREFIX}/summary', headers=LEGACY).json()['notification_drafts'] == 3
