"""M2-B lease and fencing regressions; synthetic `.onion`, NO network/Tor."""
import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select, text

from app.collector import runner, worker
from app.collector.transport import Fetched
from app.models import CrawlJob, SourceObservation
from tests.test_manual_queue_rc2 import LEGACY, REASON, enable, registered


def enqueue(client, url):
    sid = registered(client, url)
    enable(client, sid)
    response = client.post(f"/api/v1/sources/{sid}/collection/run", headers=LEGACY, json=REASON)
    assert response.status_code == 202, response.text
    return UUID(response.json()["id"]), UUID(sid)


def good_fetch(url):
    async def fetch(_url):
        assert _url == url
        return Fetched(200, "text/html", "utf-8", b"<html><title>Good</title>Minimal synthetic.</html>")
    return fetch


def test_claim_has_random_lease_and_second_claim_does_not_duplicate(client, db_session_factory, valid_onion_url):
    job_id, source_id = enqueue(client, valid_onion_url)
    claimed = worker.claim_one(db_session_factory)
    assert claimed[0:2] == (job_id, source_id)
    assert claimed[2] != job_id
    assert worker.claim_one(db_session_factory) is None
    with db_session_factory() as db:
        job = db.get(CrawlJob, job_id)
        assert job.lease_token == claimed[2]
        assert job.lease_expires_at is not None
        assert job.heartbeat_at is not None
        assert job.status == "RUNNING"


def test_renew_is_fenced_and_never_revives_finished_job(client, db_session_factory, valid_onion_url):
    job_id, _ = enqueue(client, valid_onion_url)
    _, _, token = worker.claim_one(db_session_factory)
    assert not worker.renew_lease(db_session_factory, job_id, uuid4())
    assert worker.renew_lease(db_session_factory, job_id, token)
    assert worker.fail_claimed(db_session_factory, job_id, token)
    assert not worker.renew_lease(db_session_factory, job_id, token)
    assert not worker.fail_claimed(db_session_factory, job_id, token)
    with db_session_factory() as db:
        job = db.get(CrawlJob, job_id)
        assert job.lease_token is None and job.lease_expires_at is None


def test_live_lease_is_not_recoverable_even_if_started_long_ago(
    client, db_session_factory, valid_onion_url,
):
    job_id, _ = enqueue(client, valid_onion_url)
    worker.claim_one(db_session_factory)
    with db_session_factory() as db:
        job = db.get(CrawlJob, job_id)
        job.started_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    assert worker.inspect_stale(db_session_factory, minutes=1) == 0
    assert worker.recover_stale(db_session_factory, minutes=1) == 0
    with db_session_factory() as db:
        assert db.get(CrawlJob, job_id).status == "RUNNING"


def test_expired_lease_prevents_renewal_and_reconciliation_fences_old_token(
    client, db_session_factory, valid_onion_url,
):
    job_id, _ = enqueue(client, valid_onion_url)
    _, _, token = worker.claim_one(db_session_factory)
    with db_session_factory() as db:
        job = db.get(CrawlJob, job_id)
        job.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=3)
        db.commit()
    assert not worker.renew_lease(db_session_factory, job_id, token)
    assert not worker.fail_claimed(db_session_factory, job_id, token)
    assert worker.inspect_stale(db_session_factory) == 1
    assert worker.recover_stale(db_session_factory) == 1
    assert worker.recover_stale(db_session_factory) == 0
    assert not worker.renew_lease(db_session_factory, job_id, token)
    with db_session_factory() as db:
        job = db.get(CrawlJob, job_id)
        assert job.status == "FAILED" and job.error_code == "WORKER_INTERRUPTED"
        assert job.lease_token is None


def test_direct_use_of_claimed_job_without_token_never_fetches(
    client, db_session_factory, valid_onion_url,
):
    job_id, source_id = enqueue(client, valid_onion_url)
    worker.claim_one(db_session_factory)
    called = []

    async def forbidden(url):
        called.append(url)
        raise AssertionError("No network")

    with pytest.raises(runner.NotAuthorizedError):
        asyncio.run(runner.collect_one(source_id, db_session_factory,
                                       existing_job_id=job_id, fetcher=forbidden))
    assert not called


def test_wrong_token_never_fetches_or_finalizes(client, db_session_factory, valid_onion_url):
    job_id, source_id = enqueue(client, valid_onion_url)
    worker.claim_one(db_session_factory)
    called = []

    async def forbidden(url):
        called.append(url)
        raise AssertionError("No network")

    with pytest.raises(runner.NotAuthorizedError):
        asyncio.run(runner.collect_one(source_id, db_session_factory, existing_job_id=job_id,
                                       lease_token=uuid4(), fetcher=forbidden))
    assert not called


def test_recovery_while_fetching_refuses_late_observation(
    client, db_session_factory, valid_onion_url,
):
    job_id, _ = enqueue(client, valid_onion_url)
    seen = []

    async def recovered_during_fetch(url):
        seen.append(url)
        # Simulate an operator after an abandoned/expired worker's lease.
        with db_session_factory() as db:
            job = db.get(CrawlJob, job_id)
            job.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
            job.lease_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
            db.commit()
        assert worker.recover_stale(db_session_factory) == 1
        return await good_fetch(valid_onion_url)(url)

    assert asyncio.run(worker.process_one(db_session_factory, fetcher=recovered_during_fetch))
    assert seen == [valid_onion_url]
    with db_session_factory() as db:
        job = db.get(CrawlJob, job_id)
        assert job.status == "FAILED" and job.error_code == "WORKER_INTERRUPTED"
        assert db.scalars(select(SourceObservation)).all() == []


def test_short_heartbeat_runs_during_bounded_network_fetch(
    client, db_session_factory, valid_onion_url, monkeypatch,
):
    job_id, _ = enqueue(client, valid_onion_url)
    monkeypatch.setattr(worker, "HEARTBEAT_SECONDS", 0.01)
    witnessed = []

    async def slow_fetch(url):
        await asyncio.sleep(0.07)
        with db_session_factory() as db:
            witnessed.append(db.get(CrawlJob, job_id).heartbeat_at)
        return await good_fetch(valid_onion_url)(url)

    assert asyncio.run(worker.process_one(db_session_factory, fetcher=slow_fetch))
    with db_session_factory() as db:
        job = db.get(CrawlJob, job_id)
        assert job.status == "COMPLETED"
        assert job.lease_token is None and job.lease_expires_at is None
        assert job.heartbeat_at is not None
        assert job.heartbeat_at > job.started_at
    assert witnessed and witnessed[0] is not None



def test_expired_lease_after_network_prevents_any_result_write(
    client, db_session_factory, valid_onion_url,
):
    job_id, _ = enqueue(client, valid_onion_url)

    async def expires_mid_fetch(url):
        with db_session_factory() as db:
            job = db.get(CrawlJob, job_id)
            job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        return await good_fetch(valid_onion_url)(url)

    assert asyncio.run(worker.process_one(db_session_factory, fetcher=expires_mid_fetch))
    with db_session_factory() as db:
        job = db.get(CrawlJob, job_id)
        # Operator recovery remains explicit; a stale worker must not finalize.
        assert job.status == "RUNNING"
        assert db.scalars(select(SourceObservation)).all() == []


def test_heartbeat_detects_lost_ownership_cancels_fetch_and_never_requeues(
    client, db_session_factory, valid_onion_url, monkeypatch,
):
    job_id, _ = enqueue(client, valid_onion_url)
    monkeypatch.setattr(worker, "HEARTBEAT_SECONDS", 0.01)
    monkeypatch.setattr(worker, "renew_lease", lambda *_: False)
    cancelled = []

    async def long_fetch(_url):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(worker.process_one(db_session_factory, fetcher=long_fetch))
    assert cancelled == [True]
    with db_session_factory() as db:
        assert db.get(CrawlJob, job_id).status == "RUNNING"
        assert db.scalars(select(SourceObservation)).all() == []
    # No retry has been scheduled: only an operator can reconcile the job.
    assert worker.claim_one(db_session_factory) is None


def test_stale_job_with_null_lease_from_old_release_needs_manual_recovery(
    client, db_session_factory, valid_onion_url,
):
    job_id, _ = enqueue(client, valid_onion_url)
    worker.claim_one(db_session_factory)
    with db_session_factory() as db:
        job = db.get(CrawlJob, job_id)
        job.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
        job.lease_token = None
        job.lease_expires_at = None
        db.commit()
    assert worker.inspect_stale(db_session_factory) == 1
    assert worker.recover_stale(db_session_factory) == 1
    with db_session_factory() as db:
        assert db.get(CrawlJob, job_id).error_code == "WORKER_INTERRUPTED"


def test_sqlite_migration_preserves_existing_job_rows_and_downgrades(tmp_path):
    root = Path(__file__).resolve().parents[1]
    url = f"sqlite+pysqlite:///{tmp_path / 'mig.sqlite'}"
    env = {**os.environ, "OIP_DATABASE_URL": url}

    def alembic(*args):
        result = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=root,
                                env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr

    alembic("upgrade", "0008_manual_queue")
    # The change must be additive; existing data survives the migration.
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO onion_sources (id, canonical_url, name, authorization_note, "
                       "is_active, approved_for_collection, collection_enabled) VALUES "
                       "(:id, :url, 'test', 'synthetic-only', 1, 1, 1)"),
                  {"id": "11111111111111111111111111111111", "url": "http://synthetic.onion/"})
        c.execute(text("INSERT INTO crawl_jobs (id, source_id, status) VALUES (:id, :sid, 'PENDING')"),
                  {"id": "22222222222222222222222222222222", "sid": "11111111111111111111111111111111"})
    alembic("upgrade", "head")
    with engine.connect() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0017_case_notification_drafts"
        assert c.scalar(text("SELECT status FROM crawl_jobs")) == "PENDING"
        assert c.scalar(text("SELECT lease_token FROM crawl_jobs")) is None
    alembic("downgrade", "0008_manual_queue")
    with engine.connect() as c:
        assert c.scalar(text("SELECT status FROM crawl_jobs")) == "PENDING"
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0008_manual_queue"
    engine.dispose()
