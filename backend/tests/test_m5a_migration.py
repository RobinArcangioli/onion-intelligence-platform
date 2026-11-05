"""M5-A triage migration rehearsal on an isolated disposable SQLite database."""
import os
import subprocess
import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect, text


def test_triage_upgrade_existing_indicator_and_downgrade(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    url = f"sqlite+pysqlite:///{tmp_path / 'triage.db'}"
    env = {**os.environ, 'OIP_DATABASE_URL': url}

    def alembic(*args):
        proc = subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=backend,
                              env=env, text=True, capture_output=True, timeout=60)
        assert proc.returncode == 0, proc.stdout + proc.stderr

    alembic('upgrade', '0012_observation_read_indexes')
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO onion_sources(id,canonical_url,name,authorization_note) "
                          "VALUES ('11111111111141118111111111111111','http://example.onion/','Demo','Synthetic')"))
        conn.execute(text("INSERT INTO crawl_jobs(id,source_id,status) "
                          "VALUES ('22222222222242228222222222222222','11111111111141118111111111111111','COMPLETED')"))
        conn.execute(text("INSERT INTO source_observations(id,job_id,source_id,http_status,content_type,response_bytes,text_sha256,text_length) "
                          "VALUES ('33333333333343338333333333333333','22222222222242228222222222222222',"
                          "'11111111111141118111111111111111',200,'text/plain',10,:digest,10)"), {'digest': 'a'*64})
        conn.execute(text("INSERT INTO threat_indicators(id,observation_id,source_id,indicator_type,public_reference,verification_status,confidence,evidence_codes,ruleset_version) "
                          "VALUES ('44444444444444448444444444444444','33333333333343338333333333333333',"
                          "'11111111111141118111111111111111','PUBLIC_CVE_REFERENCE','CVE-2025-12345',"
                          "'OBSERVED_REFERENCE',65,'[\"CVE_PATTERN\"]','synthetic')"))
    alembic('upgrade', 'head')
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT version_num FROM alembic_version')) == '0017_case_notification_drafts'
        row = conn.execute(text('SELECT review_status,analyst_priority FROM threat_indicators')).one()
        assert tuple(row) == ('PENDING', 'UNASSESSED')
        assert 'ix_indicator_reference_review' in {i['name'] for i in inspect(conn).get_indexes('threat_indicators')}
        assert conn.scalar(text('SELECT COUNT(*) FROM threat_indicators')) == 1
    alembic('downgrade', '0012_observation_read_indexes')
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT COUNT(*) FROM threat_indicators')) == 1
        assert 'review_status' not in {c['name'] for c in inspect(conn).get_columns('threat_indicators')}
    engine.dispose()
