"""A pre-existing lot 2 database upgrades in place without losing data."""
import os
from pathlib import Path
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, inspect, text


def _migrate(url: str, revision: str, backend_dir: Path) -> None:
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', revision],
                            cwd=backend_dir, env={**os.environ, 'OIP_DATABASE_URL': url},
                            capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr


def test_lot2_upgrade_preserves_observations_and_candidates(tmp_path: Path):
    url = f'sqlite+pysqlite:///{tmp_path / "lot2.db"}'
    backend_dir = Path(__file__).resolve().parents[1]
    _migrate(url, '0003_tor_collection', backend_dir)
    source_id, job_id, observation_id, candidate_id = [uuid.uuid4().hex for _ in range(4)]
    with create_engine(url).begin() as conn:
        conn.execute(text("""INSERT INTO onion_sources(id,canonical_url,name,authorization_note,approved_for_collection,collection_enabled)
                   VALUES (:id,'http://example.onion/','Old source','Manual check',1,0)"""), {'id':source_id})
        conn.execute(text("""INSERT INTO crawl_jobs(id,source_id,status) VALUES (:id,:source,'COMPLETED')"""),
                     {'id':job_id,'source':source_id})
        conn.execute(text("""INSERT INTO source_observations(id,job_id,source_id,http_status,content_type,response_bytes,text_sha256,text_length)
                   VALUES (:id,:job,:source,200,'text/html',128,:digest,12)"""),
                     {'id':observation_id,'job':job_id,'source':source_id,'digest':'0'*64})
        conn.execute(text("""INSERT INTO discovered_onions(id,source_id,target_url,status)
                   VALUES (:id,:source,'http://candidate.onion/','PENDING')"""),
                     {'id':candidate_id,'source':source_id})
    _migrate(url, 'head', backend_dir)
    engine = create_engine(url)
    with engine.connect() as con:
        assert con.execute(text('SELECT version_num FROM alembic_version')).scalar() == '0006_alerts_reports'
        assert con.execute(text('SELECT relevance_score,keyword_hits,change_status FROM source_observations WHERE id=:id'),
                           {'id':observation_id}).one() == (0,0,"UNKNOWN")
        assert con.execute(text('SELECT status,evidence_kind,reviewed_at FROM discovered_onions WHERE id=:id'),
                           {'id':candidate_id}).one() == ('PENDING','LINK',None)
        assert con.execute(text('SELECT collection_enabled FROM onion_sources WHERE id=:id'), {'id':source_id}).scalar() == 0
        assert {'watchlists','watchlist_rules','keyword_matches'}.issubset(set(inspect(engine).get_table_names()))
    engine.dispose()
