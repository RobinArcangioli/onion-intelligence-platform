"""Migration from v0.7 with live data preservation (SQLite simulation)."""
import os
import subprocess
import sys
from pathlib import Path
import uuid
from sqlalchemy import create_engine, inspect, text


def _upgrade(url, revision, cwd):
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', revision], cwd=cwd,
                            env={**os.environ, 'OIP_DATABASE_URL': url}, text=True,
                            capture_output=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr


def test_from_lot6_preserves_data_and_adds_auth(tmp_path):
    root = Path(__file__).resolve().parents[1]
    url = f'sqlite+pysqlite:///{tmp_path / "lot6.db"}'
    _upgrade(url, '0006_alerts_reports', root)
    sid = uuid.uuid4().hex
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text('''INSERT INTO onion_sources(id,canonical_url,name,authorization_note)
        VALUES (:s,'http://example.onion/','Existing source','Manual approval')'''), {'s': sid})
    _upgrade(url, 'head', root)
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT version_num FROM alembic_version')) == '0008_manual_queue'
        assert conn.scalar(text('SELECT name FROM onion_sources WHERE id=:s'), {'s': sid}) == 'Existing source'
        assert {'operators', 'operator_tokens', 'reports', 'audit_logs'}.issubset(
            set(inspect(engine).get_table_names()))
    engine.dispose()
