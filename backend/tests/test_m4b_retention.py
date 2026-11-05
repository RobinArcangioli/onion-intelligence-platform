"""M4-B: synthetic rows only, retention always read-only."""
from datetime import timedelta

from sqlalchemy import func, select

from app.models import (Alert, AuditLog, ClassificationResult, KeywordMatch,
                        OnionSource, SourceObservation, ThreatIndicator, IocCandidate, Report, Watchlist, WatchlistRule)
from tests.test_m4_observations import get, seed
from tests.test_manual_queue_rc2 import create_role


def test_impact_counts_dependencies_without_writing(client, db_session_factory):
    now, rows = seed(db_session_factory)
    old_source, old_obs = rows[0]
    other_source, _ = rows[3]
    # We adjust just two synthetic timestamps; leave the test date relative.
    old_time = now - timedelta(days=120)
    with db_session_factory() as db:
        old = db.get(SourceObservation, old_obs)
        old.created_at = old_time
        watch = Watchlist(name='Synthetic watchlist')
        db.add(watch); db.flush()
        rule = WatchlistRule(watchlist_id=watch.id, phrase='alpha', phrase_normalized='alpha')
        db.add(rule); db.flush()
        db.add(KeywordMatch(observation_id=old_obs, rule_id=rule.id, occurrences=1, contribution=1))
        db.add(ClassificationResult(observation_id=old_obs, source_id=old_source,
            category='NOTICE', confidence=50, evidence_codes=['RULE'],
            ruleset_version='1', review_status='PENDING'))
        db.add(ThreatIndicator(observation_id=old_obs, source_id=old_source,
            indicator_type='DOMAIN', public_reference='test', verification_status='UNVERIFIED',
            confidence=20, evidence_codes=['RULE'], ruleset_version='1'))
        db.add(IocCandidate(observation_id=old_obs, source_id=old_source,
            indicator_type='DOMAIN', normalized_value='synthetic.example.org', confidence=50,
            evidence_codes=['M5B_EXPLICIT_DOMAIN'], ruleset_version='1'))
        db.add(Alert(observation_id=old_obs, source_id=old_source, fingerprint='f'*64,
            event_type='KEYWORD', signal_code='KEYWORD', priority='LOW',
            verification_status='UNVERIFIED', relevance_score=10))
        db.add(AuditLog(actor='synthetic', action='READ', entity_type='OBSERVATION',
                        entity_id=old_obs, details='{}'))
        db.add(Report(source_id=old_source, period_start=old_time,
                      period_end=now, snapshot={'some_ref':str(old_obs)}))
        db.commit()
        before = db.scalar(select(func.count(SourceObservation.id)))
    viewer = create_role(db_session_factory, 'VIEWER')
    assert get(client, '/retention/preview?older_than_days=30', viewer).status_code == 403
    preview = get(client, '/retention/preview?older_than_days=30')
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body['observation_count'] == 1
    assert body['dependent_row_counts'] == {
        'keyword_matches':1, 'classifications':1, 'threat_indicators':1,
        'ioc_candidates':1, 'alerts':1, 'audit_entity_id_matches':1}
    assert body['report_snapshots_not_resolved'] == 1
    assert body['dry_run'] is True and body['deletion_enabled'] is False
    assert body['safe_to_purge'] is False and 'OFFSITE_RESTORE_REQUIRED' in body['blockers']
    assert str(old_obs) not in preview.text  # preview is aggregate-only
    scoped = get(client, f'/retention/preview?older_than_days=30&source_id={other_source}')
    assert scoped.status_code == 200 and scoped.json()['observation_count'] == 0
    assert all(c == 0 for c in scoped.json()['dependent_row_counts'].values())
    # Reports are deliberately unscoped, since snapshots have no relational FK.
    assert scoped.json()['report_snapshots_not_resolved'] == 1
    with db_session_factory() as db:
        assert db.scalar(select(func.count(SourceObservation.id))) == before
        assert db.get(SourceObservation, old_obs) is not None


def test_preview_invalid_parameters_never_deletes(client, db_session_factory):
    _, rows = seed(db_session_factory)
    for query in ['older_than_days=0', 'older_than_days=3651',
                  'source_id=not-a-uuid']:
        assert get(client,'/retention/preview?'+query).status_code == 422
    assert get(client, '/retention/preview?older_than_days=90').json()['observation_count'] == 0
    with db_session_factory() as db:
        assert db.scalar(select(func.count(SourceObservation.id))) == len(rows)
