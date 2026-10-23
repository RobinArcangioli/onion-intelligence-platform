"""Upgrade a real lot3 SQLite schema with existing sources/observations."""
import os
from pathlib import Path
import subprocess
import sys
import uuid
from sqlalchemy import create_engine, inspect, text


def migrate(url: str, rev: str, backend: Path) -> None:
    result = subprocess.run([sys.executable,'-m','alembic','upgrade',rev],cwd=backend,
                            env={**os.environ,'OIP_DATABASE_URL':url},capture_output=True,text=True,timeout=45)
    assert result.returncode == 0, result.stderr


def test_upgrade_lot3_to_lot4_preserves_existing_rows(tmp_path):
    url = f'sqlite+pysqlite:///{tmp_path / "legacy.db"}'
    backend = Path(__file__).resolve().parents[1]
    migrate(url,'0004_intelligence',backend)
    sid, jid, oid = (uuid.uuid4().hex for _ in range(3))
    with create_engine(url).begin() as db:
        db.execute(text("INSERT INTO onion_sources(id,canonical_url,name,authorization_note,approved_for_collection,collection_enabled) VALUES (:id,'http://example.onion/','Example','Manual check',1,0)"),{'id':sid})
        db.execute(text("INSERT INTO crawl_jobs(id,source_id,status) VALUES (:id,:sid,'COMPLETED')"), {'id':jid,'sid':sid})
        db.execute(text("INSERT INTO source_observations(id,job_id,source_id,http_status,content_type,response_bytes,text_sha256,text_length) VALUES (:id,:jid,:sid,200,'text/html',5,:digest,5)"), {'id':oid,'jid':jid,'sid':sid,'digest':'a'*64})
    migrate(url,'head',backend)
    engine=create_engine(url)
    with engine.connect() as db:
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar() == '0007_named_access'
        assert db.execute(text('SELECT text_length FROM source_observations WHERE id=:id'),{'id':oid}).scalar() == 5
        assert db.execute(text('SELECT collection_enabled FROM onion_sources WHERE id=:id'),{'id':sid}).scalar() == 0
        assert {'classification_results','threat_indicators'}.issubset(set(inspect(engine).get_table_names()))
        assert db.execute(text('SELECT count(*) FROM classification_results')).scalar() == 0
    engine.dispose()
