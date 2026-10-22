"""La migration lot 1 -> lot 2 conserve sources et choix d'activation."""
import os
import subprocess
import sys
import uuid
from pathlib import Path
from sqlalchemy import create_engine, inspect, text


def migrate(url: str, revision: str) -> None:
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run([sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", revision],
                          cwd=root, env={**os.environ, "OIP_DATABASE_URL": url},
                          capture_output=True, text=True, timeout=40)
    assert proc.returncode == 0, proc.stderr


def test_lot1_upgrade_preserves_existing_source_and_blocks_unapproved(tmp_path: Path):
    url = f"sqlite+pysqlite:///{tmp_path / 'lot1.db'}"
    migrate(url, "0002_source_lifecycle")
    uid = uuid.uuid4().hex
    engine = create_engine(url)
    with engine.begin() as con:
        con.execute(text("""
            INSERT INTO onion_sources(id, canonical_url, name, authorization_note,
                is_active, approved_for_collection, collection_enabled)
            VALUES (:id, 'http://example.onion/', 'Previously approved', 'Note historique', 1, 1, 0)
        """), {"id": uid})
    engine.dispose()
    migrate(url, "head")
    engine = create_engine(url)
    with engine.connect() as con:
        row = con.execute(text("SELECT name,approved_for_collection,collection_enabled FROM onion_sources WHERE id=:id"), {"id": uid}).one()
        assert row == ("Previously approved", 1, 0)
        assert con.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0005_cti_classification"
    assert {"crawl_jobs", "source_observations", "discovered_onions"}.issubset(set(inspect(engine).get_table_names()))
    engine.dispose()
