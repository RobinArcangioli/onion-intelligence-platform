"""M6-B additive, no-production SQLite rehearsal."""
import os
import subprocess
import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect, text


def test_m6b_up_down_on_disposable_sqlite(tmp_path):
    root = Path(__file__).resolve().parents[1]
    url = f"sqlite+pysqlite:///{tmp_path / 'm6b-rehearsal.db'}"
    env = {**os.environ, 'OIP_DATABASE_URL': url}

    def migrate(*args):
        result = subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=root,
                                env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr

    migrate('upgrade', '0015_analyst_cases')
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO onion_sources(id,canonical_url,name,authorization_note) "
                          "VALUES ('11111111111141118111111111111111','http://fixture.onion/','Fixture','approved')"))
    migrate('upgrade','head')
    with engine.begin() as conn:
        assert conn.scalar(text('SELECT version_num FROM alembic_version')) == '0019_source_pages'
        assert inspect(conn).has_table('analyst_case_notes')
        assert conn.scalar(text('SELECT COUNT(*) FROM onion_sources')) == 1
        assert {x['name'] for x in inspect(conn).get_columns('analyst_cases')} >= {'priority','version'}
        assert 'ix_case_notes_case_created' in {x['name'] for x in inspect(conn).get_indexes('analyst_case_notes')}
    migrate('downgrade','0015_analyst_cases')
    with engine.begin() as conn:
        assert not inspect(conn).has_table('analyst_case_notes')
        assert 'priority' not in {x['name'] for x in inspect(conn).get_columns('analyst_cases')}
        assert conn.scalar(text('SELECT COUNT(*) FROM onion_sources')) == 1
    engine.dispose()
