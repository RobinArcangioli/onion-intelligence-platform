"""Only disposable synthetic SQLite databases are modified."""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


def test_publication_upgrade_preserves_private_reports_and_downgrade(tmp_path):
    url=f'sqlite+pysqlite:///{tmp_path / "visitor.db"}'
    env={k:v for k,v in os.environ.items() if not k.startswith('OIP_')}
    env['OIP_DATABASE_URL']=url
    root=Path(__file__).resolve().parents[1]
    def migrate(*args):
        r=subprocess.run([sys.executable,'-m','alembic',*args],cwd=root,env=env,capture_output=True,text=True,timeout=60)
        assert r.returncode==0,r.stderr
    migrate('upgrade','0017_case_notification_drafts')
    engine=create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO reports(id,period_start,period_end,snapshot) VALUES "
                        "('11111111111141118111111111111111','2026-01-01','2026-01-02','{}')"))
    migrate('upgrade','head')
    with engine.connect() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM reports'))==1
        assert db.scalar(text('SELECT COUNT(*) FROM report_publications'))==0
        assert db.scalar(text('SELECT version_num FROM alembic_version'))=='0018_public_report_publications'
    migrate('downgrade','0017_case_notification_drafts')
    with engine.connect() as db:
        assert not inspect(db).has_table('report_publications')
        assert db.scalar(text('SELECT COUNT(*) FROM reports'))==1
    migrate('upgrade','head')
    engine.dispose()
