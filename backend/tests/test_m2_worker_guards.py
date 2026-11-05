"""M2 queue safety checks: synthetic sources, SQLite only, NO Tor/network."""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.collector import runner, worker
from app.models import AuditLog, CrawlJob, SourceObservation
from tests.test_manual_queue_rc2 import LEGACY, REASON, enable, registered


def _enqueue(client, onion_url):
    sid = registered(client, onion_url)
    enable(client, sid)
    result = client.post(f"/api/v1/sources/{sid}/collection/run", headers=LEGACY, json=REASON)
    assert result.status_code == 202
    return UUID(result.json()["id"]), sid


def test_total_fetch_deadline_fails_closed_and_preserves_no_observation(
    client, db_session_factory, valid_onion_url, monkeypatch,
):
    job_id, _ = _enqueue(client, valid_onion_url)
    monkeypatch.setattr(runner, "MAX_FETCH_SECONDS", 0.01)
    seen = []

    async def deliberately_slow_fetch(url):
        seen.append(url)
        await asyncio.sleep(0.1)
        raise AssertionError("must be cancelled before returning content")

    assert asyncio.run(worker.process_one(db_session_factory, fetcher=deliberately_slow_fetch))
    assert seen == [valid_onion_url]
    with db_session_factory() as db:
        job = db.get(CrawlJob, job_id)
        assert job.status == "FAILED"
        assert job.error_code == "FETCH_TIMEOUT"
        assert job.finished_at is not None
        assert db.scalar(select(func.count()).select_from(SourceObservation)) == 0
        assert db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "collection.failed",
        )) == 1
    # A failed one-shot never retries by itself or visits another URL.
    assert asyncio.run(worker.process_one(db_session_factory, fetcher=deliberately_slow_fetch)) is False
    assert len(seen) == 1


def test_inspect_stale_is_read_only_and_recovery_idempotent(
    client, db_session_factory, valid_onion_url,
):
    job_id, _ = _enqueue(client, valid_onion_url)
    assert worker.claim_one(db_session_factory)[0] == job_id
    with db_session_factory() as db:
        job = db.get(CrawlJob, job_id)
        job.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        db.commit()
    assert worker.inspect_stale(db_session_factory) == 1
    assert worker.inspect_stale(db_session_factory) == 1
    with db_session_factory() as db:
        assert db.get(CrawlJob, job_id).status == "RUNNING"
        assert db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "collection.abandoned",
        )) == 0
    assert worker.recover_stale(db_session_factory) == 1
    assert worker.recover_stale(db_session_factory) == 0
    assert worker.inspect_stale(db_session_factory) == 0
    with db_session_factory() as db:
        job = db.get(CrawlJob, job_id)
        assert job.status == "FAILED"
        assert job.error_code == "WORKER_INTERRUPTED"
        assert db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "collection.abandoned",
        )) == 1


@pytest.mark.parametrize("minutes", (0, -1, 10081))
def test_stale_cutoff_rejects_out_of_bounds(db_session_factory, minutes):
    with pytest.raises(ValueError):
        worker.inspect_stale(db_session_factory, minutes=minutes)
    with pytest.raises(ValueError):
        worker.recover_stale(db_session_factory, minutes=minutes)


def test_recovery_requires_explicit_attestation(monkeypatch):
    # Must fail before any database access, without accepting a Tor env flag.
    monkeypatch.setattr(sys, "argv", ["worker", "--recover-stale"])
    monkeypatch.delenv("OIP_TOR_COLLECTION_ENABLED", raising=False)
    with pytest.raises(SystemExit) as exc:
        worker.main()
    assert exc.value.code == 2


def test_normal_worker_stays_disabled_without_tor_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["worker", "--once"])
    monkeypatch.delenv("OIP_TOR_COLLECTION_ENABLED", raising=False)
    assert worker.main() == 2


def test_inspect_mode_without_tor_flag_uses_database_only(monkeypatch, db_session_factory, capsys):
    class FakeEngine:
        def dispose(self):
            pass

    fake_engine = FakeEngine()
    monkeypatch.setattr(sys, "argv", ["worker", "--inspect-stale"])
    monkeypatch.setenv("OIP_DATABASE_URL", "sqlite+pysqlite:///synthetic")
    monkeypatch.delenv("OIP_TOR_COLLECTION_ENABLED", raising=False)
    monkeypatch.setattr(worker, "create_engine", lambda _url, **_kwargs: fake_engine)
    monkeypatch.setattr(worker, "sessionmaker", lambda **_kwargs: db_session_factory)
    assert worker.main() == 0
    assert "stale_running_jobs=0" in capsys.readouterr().out
