"""Migration from the operator's v0.5.0 schema with historical CTI data."""
import os
from pathlib import Path
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, inspect, text


def upgrade(url: str, revision: str, backend: Path):
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', revision],
                            cwd=backend, env={**os.environ, 'OIP_DATABASE_URL': url},
                            capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr


def test_upgrade_from_lot4_preserves_existing_data(tmp_path):
    url = f'sqlite+pysqlite:///{tmp_path / "legacy_lot4.db"}'
    backend = Path(__file__).resolve().parents[1]
    upgrade(url, '0005_cti_classification', backend)
    sid, jid, oid, iid = (uuid.uuid4().hex for _ in range(4))
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO onion_sources(id,canonical_url,name,authorization_note) VALUES (:s,'http://example.onion/','Legacy','Manual check')"), {'s':sid})
        db.execute(text("INSERT INTO crawl_jobs(id,source_id,status) VALUES (:j,:s,'COMPLETED')"), {'j':jid,'s':sid})
        db.execute(text("INSERT INTO source_observations(id,job_id,source_id,http_status,content_type,response_bytes,text_sha256,text_length) VALUES (:o,:j,:s,200,'text/html',1,:hash,1)"), {'o':oid,'j':jid,'s':sid,'hash':'a'*64})
        db.execute(text("INSERT INTO threat_indicators(id,observation_id,source_id,indicator_type,public_reference,verification_status,confidence,evidence_codes,ruleset_version) VALUES (:i,:o,:s,'PUBLIC_CVE_REFERENCE','CVE-2025-12345','OBSERVED_REFERENCE',55,'[]','1.0')"), {'i':iid,'o':oid,'s':sid})
    upgrade(url, 'head', backend)
    with engine.connect() as db:
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar() == '0008_manual_queue'
        assert db.execute(text('SELECT count(*) FROM threat_indicators')).scalar() == 1
        assert db.execute(text('SELECT text_sha256 FROM source_observations WHERE id=:o'),{'o':oid}).scalar() == 'a'*64
        assert db.execute(text('SELECT count(*) FROM alerts')).scalar() == 0
        assert {'alerts','reports'}.issubset(set(inspect(engine).get_table_names()))
    engine.dispose()
