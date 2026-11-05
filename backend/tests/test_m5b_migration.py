"""Rehearse additive M5-B upgrade/downgrade only on disposable SQLite."""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


def test_existing_cti_preserved_and_ioc_table_is_additive(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    dsn = f"sqlite+pysqlite:///{tmp_path / 'm5b.db'}"
    env = {**os.environ, 'OIP_DATABASE_URL': dsn}

    def upgrade(*args):
        proc = subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=backend,
                              env=env, capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stdout + proc.stderr

    upgrade('upgrade', '0013_indicator_triage')
    engine = create_engine(dsn)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO onion_sources(id,canonical_url,name,authorization_note) "
                                "VALUES ('11111111111141118111111111111111','http://synthetic.onion/','Synthetic','approved')"))
        connection.execute(text("INSERT INTO crawl_jobs(id,source_id,status) "
                                "VALUES ('22222222222242228222222222222222','11111111111141118111111111111111','COMPLETED')"))
        connection.execute(text("INSERT INTO source_observations(id,job_id,source_id,http_status,content_type,response_bytes,text_sha256,text_length) "
                                "VALUES ('33333333333343338333333333333333','22222222222242228222222222222222',"
                                "'11111111111141118111111111111111',200,'text/plain',10,:hash,10)"), {'hash': 'a'*64})
        connection.execute(text("INSERT INTO threat_indicators(id,observation_id,source_id,indicator_type,public_reference,verification_status,confidence,evidence_codes,ruleset_version) "
                                "VALUES ('44444444444444448444444444444444','33333333333343338333333333333333',"
                                "'11111111111141118111111111111111','PUBLIC_CVE_REFERENCE','CVE-2025-12345',"
                                "'OBSERVED_REFERENCE',65,'[\"CVE_PATTERN\"]','1')"))
    upgrade('upgrade', 'head')
    with engine.begin() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0018_public_report_publications'
        assert connection.scalar(text('SELECT COUNT(*) FROM threat_indicators')) == 1
        indexes = {row['name'] for row in inspect(connection).get_indexes('ioc_candidates')}
        assert {'ix_ioc_candidate_source_created', 'ix_ioc_candidate_review',
                'ix_ioc_candidate_type_value_review'} <= indexes
        connection.execute(text("INSERT INTO ioc_candidates(id,observation_id,source_id,indicator_type,normalized_value,confidence,evidence_codes,ruleset_version) "
                                "VALUES ('55555555555545558555555555555555','33333333333343338333333333333333',"
                                "'11111111111141118111111111111111','SHA256',:digest,50,'[\"M5B_EXPLICIT_SHA256\"]','1')"),
                           {'digest': 'f'*64})
        assert connection.scalar(text("SELECT review_status FROM ioc_candidates")) == 'PENDING'
    upgrade('downgrade', '0013_indicator_triage')
    with engine.connect() as connection:
        assert not inspect(connection).has_table('ioc_candidates')
        assert connection.scalar(text('SELECT COUNT(*) FROM threat_indicators')) == 1
        assert connection.scalar(text('SELECT COUNT(*) FROM source_observations')) == 1
    engine.dispose()
