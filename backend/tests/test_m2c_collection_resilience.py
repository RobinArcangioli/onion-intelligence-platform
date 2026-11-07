"""M2-C offline quota, circuit, stop and metrics regression (no real Onion)."""
import asyncio
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import select

from app.collector import worker
from app.collector.policy import read_policy
from app.models import CrawlJob, SourceObservation
from tests.test_manual_queue_rc2 import LEGACY, REASON, enable, registered, create_role


def second_synthetic_root():
    key = bytes(reversed(range(32)))
    checksum = hashlib.sha3_256(b'.onion checksum' + key + b'\x03').digest()[:2]
    return 'http://' + base64.b32encode(key + checksum + b'\x03').decode().lower().rstrip('=') + '.onion/'


def queue(client, sid):
    return client.post(f'/api/v1/sources/{sid}/collection/run', headers=LEGACY, json=REASON)


def test_source_cooldown_blocks_repeated_click_after_completion(client, db_session_factory, valid_onion_url):
    sid = registered(client, valid_onion_url)
    enable(client, sid)
    assert queue(client, sid).status_code == 202
    _, _, token = worker.claim_one(db_session_factory)
    with db_session_factory() as db:
        job = db.scalar(select(CrawlJob))
        assert worker.fail_claimed(db_session_factory, job.id, token)
    response = queue(client, sid)
    assert response.status_code == 429 and response.json()['detail'] == 'SOURCE_COOLDOWN'


def test_global_pending_quota_blocks_second_source(client, valid_onion_url, monkeypatch):
    monkeypatch.setenv('OIP_COLLECTION_MAX_PENDING', '1')
    sid1 = registered(client, valid_onion_url)
    sid2 = registered(client, second_synthetic_root())
    enable(client, sid1)
    enable(client, sid2)
    assert queue(client, sid1).status_code == 202
    denied = queue(client, sid2)
    assert denied.status_code == 429 and denied.json()['detail'] == 'GLOBAL_QUEUE_FULL'


def test_emergency_stop_blocks_enqueue_and_claim(client, db_session_factory, valid_onion_url, monkeypatch):
    sid = registered(client, valid_onion_url)
    enable(client, sid)
    assert queue(client, sid).status_code == 202
    monkeypatch.setenv('OIP_COLLECTION_EMERGENCY_STOP', 'true')
    denied = queue(client, sid)
    assert denied.status_code == 503
    assert worker.claim_one(db_session_factory) is None
    with db_session_factory() as db:
        assert db.scalar(select(CrawlJob)).status == 'PENDING'


def test_running_cap_is_global_and_pending_remains_pending(client, db_session_factory, valid_onion_url, monkeypatch):
    monkeypatch.setenv('OIP_COLLECTION_MAX_RUNNING', '1')
    sid1 = registered(client, valid_onion_url)
    sid2 = registered(client, second_synthetic_root())
    enable(client, sid1)
    enable(client, sid2)
    first = queue(client, sid1).json()['id']
    second = queue(client, sid2).json()['id']
    claimed = worker.claim_one(db_session_factory)
    assert claimed[0] in (UUID(first), UUID(second))
    assert worker.claim_one(db_session_factory) is None
    with db_session_factory() as db:
        other = UUID(second) if claimed[0] == UUID(first) else UUID(first)
        assert db.get(CrawlJob, other).status == 'PENDING'


def test_circuit_opens_for_three_consecutive_network_errors_and_expires(
    client, db_session_factory, valid_onion_url, monkeypatch,
):
    monkeypatch.setenv('OIP_COLLECTION_SOURCE_COOLDOWN_SECONDS', '0')
    sid = registered(client, valid_onion_url)
    enable(client, sid)
    for i in range(3):
        response = queue(client, sid)
        assert response.status_code == 202
        job_id, _, token = worker.claim_one(db_session_factory)
        with db_session_factory() as db:
            job = db.get(CrawlJob, job_id)
            job.status = 'FAILED'
            job.error_code = 'TOR_NETWORK_ERROR'
            job.finished_at = datetime.now(timezone.utc) - timedelta(seconds=10-i)
            job.lease_token = None
            job.lease_expires_at = None
            db.commit()
    denied = queue(client, sid)
    assert denied.status_code == 429 and denied.json()['detail'] == 'CIRCUIT_OPEN'
    progress = client.get(f'/api/v1/sources/{sid}/collection/progress', headers=LEGACY).json()
    assert progress["restriction"] == "CIRCUIT_OPEN"
    retry_at = datetime.fromisoformat(denied.headers["X-OIP-Retry-At"])
    assert retry_at == datetime.fromisoformat(progress["retry_at"])
    assert retry_at > datetime.now(timezone.utc) + timedelta(minutes=59)
    with db_session_factory() as db:
        for job in db.scalars(select(CrawlJob)).all():
            job.finished_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db.commit()
    assert queue(client, sid).status_code == 202


def test_success_resets_consecutive_failure_circuit(client, db_session_factory, valid_onion_url, monkeypatch):
    monkeypatch.setenv('OIP_COLLECTION_SOURCE_COOLDOWN_SECONDS', '0')
    sid = registered(client, valid_onion_url)
    enable(client, sid)
    for i, status in enumerate(['FAILED', 'COMPLETED', 'FAILED', 'FAILED']):
        job = queue(client, sid)
        assert job.status_code == 202
        with db_session_factory() as db:
            active = db.get(CrawlJob, UUID(job.json()['id']))
            active.status = status
            active.error_code = 'TOR_NETWORK_ERROR' if status == 'FAILED' else None
            active.finished_at = datetime.now(timezone.utc)
            # Deterministic order when clock timestamps are too close.
            active.created_at = datetime.now(timezone.utc) + timedelta(seconds=i)
            db.commit()
    assert queue(client, sid).status_code == 202


def test_config_fails_closed_on_bad_limit_and_boolean(monkeypatch):
    monkeypatch.setenv('OIP_COLLECTION_MAX_PENDING', '0')
    with pytest.raises(ValueError, match='OIP_COLLECTION_MAX_PENDING'):
        read_policy()
    monkeypatch.setenv('OIP_COLLECTION_MAX_PENDING', '25')
    monkeypatch.setenv('OIP_COLLECTION_EMERGENCY_STOP', 'anything')
    with pytest.raises(ValueError, match='OIP_COLLECTION_EMERGENCY_STOP'):
        read_policy()


def test_metrics_aggregated_and_admin_only(client, db_session_factory, valid_onion_url):
    sid = registered(client, valid_onion_url)
    enable(client, sid)
    assert queue(client, sid).status_code == 202
    viewer = create_role(db_session_factory, 'VIEWER')
    assert client.get('/api/v1/collection/metrics').status_code == 401
    assert client.get('/api/v1/collection/metrics', headers=viewer).status_code == 403
    res = client.get('/api/v1/collection/metrics', headers=LEGACY)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data['jobs']['PENDING'] == 1
    assert data['oldest_pending_seconds'] is not None
    assert data['failed_24h'] == 0
    assert 'url' not in res.text.lower() and 'token' not in res.text.lower()


def test_running_stop_cancels_fetch_without_observation(client, db_session_factory, valid_onion_url, monkeypatch):
    sid = registered(client, valid_onion_url)
    enable(client, sid)
    assert queue(client, sid).status_code == 202
    monkeypatch.setattr(worker, 'HEARTBEAT_SECONDS', 0.01)
    cancelled = []

    async def hanging(_url):
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    async def set_stop():
        async def stop_soon():
            await asyncio.sleep(0.04)
            monkeypatch.setenv('OIP_COLLECTION_EMERGENCY_STOP', 'true')
        task = asyncio.create_task(stop_soon())
        try:
            await worker.process_one(db_session_factory, fetcher=hanging)
        finally:
            await task

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(set_stop())
    assert cancelled == [True]
    with db_session_factory() as db:
        assert db.scalar(select(CrawlJob)).status == 'RUNNING'
        assert db.scalars(select(SourceObservation)).all() == []


def test_worker_local_sentinel_works_without_container_restart(
    client, db_session_factory, valid_onion_url, monkeypatch, tmp_path,
):
    sid = registered(client, valid_onion_url)
    enable(client, sid)
    assert queue(client, sid).status_code == 202
    sentinel = tmp_path / 'emergency-stop'
    monkeypatch.setenv('OIP_COLLECTION_KILL_FILE', str(sentinel))
    sentinel.touch()
    assert worker.claim_one(db_session_factory) is None
    assert queue(client, sid).status_code == 503
    with db_session_factory() as db:
        assert db.scalar(select(CrawlJob)).status == 'PENDING'


def test_bad_kill_file_is_fail_closed(client, valid_onion_url, monkeypatch):
    sid = registered(client, valid_onion_url)
    enable(client, sid)
    monkeypatch.setenv('OIP_COLLECTION_KILL_FILE', 'relative/path')
    assert queue(client, sid).status_code == 503


def test_sentinel_raised_during_fetch_blocks_observation(
    client, db_session_factory, valid_onion_url, monkeypatch, tmp_path,
):
    sid = registered(client, valid_onion_url)
    enable(client, sid)
    job = queue(client, sid)
    assert job.status_code == 202
    sentinel = tmp_path / 'oip-halted'
    monkeypatch.setenv('OIP_COLLECTION_KILL_FILE', str(sentinel))

    async def synth_fetch(_url):
        sentinel.touch()
        from app.collector.transport import Fetched
        return Fetched(200, 'text/html', 'utf-8', b'<html>TEST</html>')

    assert asyncio.run(worker.process_one(db_session_factory, fetcher=synth_fetch))
    with db_session_factory() as db:
        assert db.get(CrawlJob, UUID(job.json()['id'])).status == 'RUNNING'
        assert db.scalars(select(SourceObservation)).all() == []
