"""Transactional index migration rehearsal against a disposable SQLite DB."""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


def test_index_upgrade_downgrade_preserves_rows(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    url = f"sqlite+pysqlite:///{tmp_path / 'index-test.db'}"
    env = {**os.environ, 'OIP_DATABASE_URL': url}

    def alembic(*args):
        completed = subprocess.run([sys.executable, '-m', 'alembic', *args],
                                   cwd=backend, env=env, capture_output=True,
                                   text=True, timeout=60)
        assert completed.returncode == 0, completed.stdout + completed.stderr

    alembic('upgrade', '0011_observation_metadata_fts')
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO onion_sources(id,canonical_url,name,authorization_note) "
                          "VALUES ('11111111111141118111111111111111','http://example.onion/', 'Example', 'Synthetic')"))
        conn.execute(text("INSERT INTO crawl_jobs(id,source_id,status) "
                          "VALUES ('22222222222242228222222222222222','11111111111141118111111111111111','COMPLETED')"))
        conn.execute(text("INSERT INTO source_observations(id,job_id,source_id,http_status,content_type,"
                          "response_bytes,text_sha256,text_length) VALUES "
                          "('33333333333343338333333333333333','22222222222242228222222222222222',"
                          "'11111111111141118111111111111111',200,'text/plain',5,:sha,5)"), {'sha':'c'*64})
    alembic('upgrade', 'head')
    with engine.connect() as conn:
        indexes = {i['name'] for i in inspect(conn).get_indexes('source_observations')}
        assert {'ix_obs_recent_id_desc','ix_obs_source_recent_id_desc',
                'ix_obs_hash_recent_id_desc'} <= indexes
        assert 'ix_alerts_observation_id' in {i['name'] for i in inspect(conn).get_indexes('alerts')}
        assert 'ix_audit_logs_entity_id' in {i['name'] for i in inspect(conn).get_indexes('audit_logs')}
        assert conn.scalar(text('SELECT count(*) FROM source_observations')) == 1
        assert conn.scalar(text('SELECT version_num FROM alembic_version')) == '0020_collection_batches'
    alembic('downgrade', '0011_observation_metadata_fts')
    with engine.connect() as conn:
        indexes = {i['name'] for i in inspect(conn).get_indexes('source_observations')}
        assert 'ix_obs_recent_id_desc' not in indexes
        assert conn.scalar(text('SELECT count(*) FROM source_observations')) == 1
    engine.dispose()
