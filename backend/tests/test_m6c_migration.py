"""Disposable SQLite Alembic rehearsal only: NOT a substitute for PostgreSQL 17."""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


def test_m6c_up_down_on_disposable_sqlite(tmp_path):
    root = Path(__file__).resolve().parents[1]
    url = f"sqlite+pysqlite:///{tmp_path / 'm6c.db'}"
    env = {**os.environ, "OIP_DATABASE_URL": url}

    def migrate(*args):
        result = subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=root,
                                env=env, capture_output=True, text=True, timeout=70)
        assert result.returncode == 0, result.stdout + result.stderr

    migrate('upgrade', '0016_case_triage_notes')
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO onion_sources(id,canonical_url,name,authorization_note) "
                          "VALUES ('11111111111141118111111111111111','http://fixture.onion/','Fixture','approved')"))
    migrate('upgrade', 'head')
    with engine.begin() as conn:
        assert conn.scalar(text('SELECT version_num FROM alembic_version')) == '0018_public_report_publications'
        assert inspect(conn).has_table('case_notification_policies')
        assert inspect(conn).has_table('case_notification_drafts')
        assert conn.scalar(text('SELECT COUNT(*) FROM onion_sources')) == 1
    migrate('downgrade', '0016_case_triage_notes')
    with engine.begin() as conn:
        assert not inspect(conn).has_table('case_notification_policies')
        assert not inspect(conn).has_table('case_notification_drafts')
        assert conn.scalar(text('SELECT COUNT(*) FROM onion_sources')) == 1
    engine.dispose()
