"""Offline SQLite migration rehearsal, never an instruction to downgrade prod."""
import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text


def test_m4_additive_index_migration_keeps_observations(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    url = f"sqlite+pysqlite:///{tmp_path / 'm4.db'}"
    env = {**os.environ, 'OIP_DATABASE_URL': url}

    def alembic(*args):
        result = subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=backend,
                                env=env, capture_output=True, text=True, timeout=50)
        assert result.returncode == 0, result.stdout + result.stderr

    alembic('upgrade', '0010_governed_schedules')
    engine = create_engine(url)
    with engine.begin() as conn:
        sid, jid, oid = [uuid.uuid4().hex for _ in range(3)]
        conn.execute(text("INSERT INTO onion_sources(id, canonical_url, name, authorization_note) "
                          "VALUES (:id,'http://synthetic.onion/', 'Synthetic', 'Test authorization')"), {'id':sid})
        conn.execute(text("INSERT INTO crawl_jobs(id,source_id,status) VALUES (:id,:source,'COMPLETED')"),
                     {'id':jid,'source':sid})
        conn.execute(text("INSERT INTO source_observations(id,job_id,source_id,http_status,content_type,response_bytes,"
                          "text_sha256,text_length) VALUES (:id,:job,:source,200,'text/html',22,:sha,7)"),
                     {'id':oid,'job':jid,'source':sid,'sha':'f'*64})
    alembic('upgrade','0011_observation_metadata_fts')
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM source_observations')) == 1
        assert conn.scalar(text('SELECT version_num FROM alembic_version')) == '0011_observation_metadata_fts'
    alembic('downgrade','0010_governed_schedules')
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM source_observations')) == 1
    engine.dispose()
