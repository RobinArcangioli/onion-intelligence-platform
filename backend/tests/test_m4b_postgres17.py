"""Optional PostgreSQL 17 integration/plan rehearsal on an EMPTY local test DB.

This test refuses production/remote DSNs. It never contacts Tor or OVH.
Set OIP_M4B_TEST_DSN only for a fresh disposable oip_m4b_test database.
"""
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, insert, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models import CrawlJob, OnionSource, SourceObservation, IocCandidate
from app.observation_history.service import search
from app.observation_history.retention import impact_preview


def test_postgres17_migrations_search_and_explain():
    raw_dsn = os.environ.get('OIP_M4B_TEST_DSN')
    if not raw_dsn:
        if os.environ.get('OIP_M4B_REQUIRE_DATABASE') == '1':
            pytest.fail('PostgreSQL 17 M4-B integration was required but the test DSN is missing')
        pytest.skip('No dedicated local PostgreSQL 17 test DSN provided')
    url = make_url(raw_dsn)
    # Exact-name + loopback + no advanced connection parameters: guardrails
    # against accidental migration of a live or reachable remote database.
    assert (url.drivername == 'postgresql+psycopg'
            and url.database == 'oip_m4b_test'
            and url.host in ('localhost', '127.0.0.1', '::1')
            and url.username == 'oip_test' and bool(url.password)
            and url.port in (None, 5432) and not url.query), 'Refusing an unsafe PostgreSQL test DSN'
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            assert conn.dialect.server_version_info[0] == 17, 'PostgreSQL 17 is required'
            existing = conn.scalar(text("SELECT COUNT(*) FROM information_schema.tables "
                                        "WHERE table_schema='public' AND table_type='BASE TABLE'"))
            assert existing == 0, 'Use a newly created EMPTY disposable test database'
        backend = Path(__file__).resolve().parents[1]
        env = {**os.environ, 'OIP_DATABASE_URL': raw_dsn}
        upgraded = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                                  cwd=backend, env=env, capture_output=True,
                                  text=True, timeout=120)
        assert upgraded.returncode == 0, 'Alembic upgrade failed (see local test logs)'
        with Session(engine, autoflush=False) as db:
            names = {row[0]: row[1] for row in db.execute(text(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' "
                "AND tablename='source_observations'"))}
            for name in ('ix_obs_recent_id_desc', 'ix_obs_source_recent_id_desc',
                         'ix_obs_hash_recent_id_desc'):
                assert name in names and 'DESC' in names[name]
            assert 'using gin' in names['ix_observation_metadata_search'].lower()
            assert db.scalar(text("SELECT COUNT(*) FROM pg_indexes WHERE schemaname='public' "
                                  "AND indexname IN ('ix_alerts_observation_id', 'ix_audit_logs_entity_id')")) == 2
            # M5-A migration is part of HEAD and must index public-reference triage.
            assert db.scalar(text("SELECT COUNT(*) FROM pg_indexes WHERE schemaname='public' "
                                  "AND indexname='ix_indicator_reference_review'")) == 1
            assert db.scalar(text("SELECT COUNT(*) FROM pg_indexes WHERE schemaname='public' "
                                  "AND indexname IN ('ix_ioc_candidate_review', "
                                  "'ix_ioc_candidate_type_value_review')")) == 2
            sid = uuid.uuid4()
            db.execute(insert(OnionSource), [{'id':sid, 'canonical_url':'http://synthetic-test.onion/',
                'name':'Synthetic source', 'category':'FORUM', 'authorization_note':'Synthetic only'}])
            now = datetime.now(timezone.utc)
            jobs = []
            obs = []
            for i in range(400):
                job = uuid.uuid4()
                jobs.append({'id':job, 'source_id':sid, 'status':'COMPLETED'})
                obs.append({'id':uuid.uuid4(), 'job_id':job, 'source_id':sid,
                    'http_status':200, 'content_type':'text/plain', 'response_bytes':50,
                    'title': 'alpha diagnostic' if i % 4 == 0 else 'bravo diagnostic',
                    'description': 'Synthetic description without page text',
                    'text_sha256':f'{i:064x}', 'text_length':50,
                    'change_status':'MODIFIED' if i % 4 == 0 else 'UNCHANGED',
                    'created_at':now-timedelta(days=i)})
            db.execute(insert(CrawlJob), jobs)
            db.execute(insert(SourceObservation), obs)
            db.execute(insert(IocCandidate), [{'observation_id':obs[0]['id'], 'source_id':sid,
                'indicator_type':'DOMAIN','normalized_value':'synthetic.example.org',
                'confidence':50,'evidence_codes':['M5B_EXPLICIT_DOMAIN'],
                'ruleset_version':'2026-10-m5b-explicit-v1'}])
            db.commit()
            result = search(db, source_id=sid, category='FORUM', status='MODIFIED',
                            since=None, until=None, q='alpha', sha256=None,
                            limit=20, offset=0)
            assert result['total'] == 100 and len(result['items']) == 20
            assert result['items'][0]['title'] == 'alpha diagnostic'
            preview = impact_preview(db, cutoff=now-timedelta(days=201),
                                     older_than_days=201, source_id=sid)
            assert preview['observation_count'] == 198
            assert preview['dependent_row_counts']['ioc_candidates'] == 0
            assert preview['safe_to_purge'] is False
            # Planner statistics are evidence, not a latency SLO. Real plans
            # depend on data size, autovacuum, storage and visibility maps.
            db.execute(text('ANALYZE source_observations'))
            plan = db.execute(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                                   "SELECT id FROM source_observations "
                                   "WHERE source_id=:sid ORDER BY created_at DESC,id DESC LIMIT 20"),
                              {'sid':sid}).scalar_one()
            assert plan[0]['Plan']['Actual Rows'] == 20
            assert plan[0]['Execution Time'] >= 0
            print('M4B_POSTGRES17_EXPLAIN_MS=', plan[0]['Execution Time'])
    finally:
        engine.dispose()
