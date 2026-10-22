"""Test d'Alembic sur SQLite : PostgreSQL réel reste à valider via Docker."""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect


def test_initial_migration_on_sqlite(tmp_path: Path):
    database = tmp_path / "migration.db"
    url = f"sqlite+pysqlite:///{database}"
    backend_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=backend_dir,
        env={**os.environ, "OIP_DATABASE_URL": url},
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert {"onion_sources", "audit_logs", "alembic_version"}.issubset(tables)
    engine.dispose()
