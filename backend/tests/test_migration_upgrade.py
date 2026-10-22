"""Migration d'une base préexistante v0.1 vers le lot 1, sans perte."""
import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


def run_migration(url: str, revision: str) -> None:
    base = Path(__file__).resolve().parents[1]
    p = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", revision],
        cwd=base, env={**os.environ, "OIP_DATABASE_URL": url},
        capture_output=True, text=True, timeout=40,
    )
    assert p.returncode == 0, p.stdout + p.stderr


def test_lot0_upgrade_preserves_sources(tmp_path: Path):
    url = f"sqlite+pysqlite:///{tmp_path / 'old.db'}"
    run_migration(url, "0001_bootstrap")
    engine = create_engine(url)
    fake = str(uuid.uuid4()).replace("-", "")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO onion_sources(id,canonical_url,name,authorization_note)
            VALUES(:id,'http://example.onion/','Source existante','Autorisation déjà documentée')
        """), {"id": fake})
    run_migration(url, "head")
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT name,is_active,priority,approved_for_collection,collection_enabled,deleted_at
            FROM onion_sources WHERE id = :id
        """), {"id": fake}).one()
        assert row[0] == "Source existante"
        assert row[1] == 1
        assert row[2] == 3
        assert row[3] == 1
        assert row[4] == 0
        assert row[5] is None
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0005_cti_classification"
    assert "details" in {col["name"] for col in inspect(engine).get_columns("audit_logs")}
    engine.dispose()
