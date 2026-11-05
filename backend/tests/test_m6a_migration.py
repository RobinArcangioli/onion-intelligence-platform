"""SQLite-only additive migration rehearsal. Never target production."""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


def test_m6a_upgrade_and_explicit_test_downgrade(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    db_url = f"sqlite+pysqlite:///{tmp_path / 'm6a-test.db'}"
    env = {**os.environ, 'OIP_DATABASE_URL': db_url}

    def alembic(*args):
        result = subprocess.run([sys.executable,'-m','alembic',*args],cwd=backend,env=env,
                                capture_output=True,text=True,timeout=60)
        assert result.returncode == 0, result.stdout+result.stderr

    alembic('upgrade','0014_ioc_candidates')
    engine = create_engine(db_url)
    with engine.begin() as con:
        con.execute(text("INSERT INTO onion_sources(id,canonical_url,name,authorization_note) "
                         "VALUES ('11111111111141118111111111111111','http://fixture.onion/','Fixture','approved')"))
    alembic('upgrade','head')
    with engine.begin() as con:
        assert con.scalar(text('SELECT version_num FROM alembic_version')) == '0018_public_report_publications'
        assert inspect(con).has_table('analyst_cases') and inspect(con).has_table('analyst_case_events')
        assert con.scalar(text('SELECT COUNT(*) FROM onion_sources')) == 1
        case_indexes={idx['name'] for idx in inspect(con).get_indexes('analyst_cases')}
        assert 'ix_analyst_cases_status_updated' in case_indexes
        assert 'ix_analyst_cases_assignee_updated' in case_indexes
    alembic('downgrade','0014_ioc_candidates')
    with engine.connect() as con:
        assert not inspect(con).has_table('analyst_cases')
        assert not inspect(con).has_table('analyst_case_events')
        assert con.scalar(text('SELECT COUNT(*) FROM onion_sources')) == 1
    engine.dispose()
