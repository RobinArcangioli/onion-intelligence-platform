"""M3 migration preserves existing sources/jobs and downgrades only in an isolated DB."""
import os
import subprocess
import sys
import uuid
from pathlib import Path
from sqlalchemy import create_engine, inspect, text


def test_m3_additive_migration_on_synthetic_sqlite(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    url = f"sqlite+pysqlite:///{tmp_path / 'm3.db'}"
    env = {**os.environ, "OIP_DATABASE_URL": url}

    def alembic(*args):
        p = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=backend, env=env,
                           capture_output=True, text=True, timeout=50)
        assert p.returncode == 0, p.stdout + p.stderr

    alembic("upgrade", "0009_job_leases")
    source_id, job_id = uuid.uuid4().hex, uuid.uuid4().hex
    db = create_engine(url)
    with db.begin() as conn:
        conn.execute(text("INSERT INTO onion_sources(id,canonical_url,name,authorization_note) "
                          "VALUES (:id,'http://synthetic.onion/','Synthetic source','Manual approval')"), {"id": source_id})
        conn.execute(text("INSERT INTO crawl_jobs(id,source_id,status) VALUES (:j,:s,'COMPLETED')"),
                     {"j": job_id, "s": source_id})
    alembic("upgrade", "0010_governed_schedules")
    with db.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM source_schedules")) == 0
        assert conn.scalar(text("SELECT count(*) FROM schedule_decisions")) == 0
        assert conn.scalar(text("SELECT count(*) FROM crawl_jobs")) == 1
        assert "source_schedules" in inspect(db).get_table_names()
    alembic("downgrade", "0009_job_leases")
    with db.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM crawl_jobs")) == 1
        assert "source_schedules" not in inspect(db).get_table_names()
    db.dispose()
