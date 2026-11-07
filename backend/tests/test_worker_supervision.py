"""Supervision must separate a blocked queue from normal URL sequencing."""
from datetime import datetime, timedelta, timezone
import uuid

from app.collector.monitor import queue_issues, socks_ready
from app.models import CrawlJob, OnionSource


def test_waiting_sibling_is_not_stuck_but_stale_lease_and_eligible_job_are_reported(
    db_session_factory, valid_onion_url, monkeypatch,
):
    monkeypatch.setenv("OIP_COLLECTION_MAX_RUNNING", "2")
    now = datetime.now(timezone.utc)
    batch = uuid.uuid4()
    with db_session_factory.begin() as db:
        source = OnionSource(name="Synthetic monitor group", canonical_url=valid_onion_url,
                             authorization_note="Local test")
        db.add(source)
        db.flush()
        running = CrawlJob(source_id=source.id, batch_id=batch, status="RUNNING",
                           created_at=now-timedelta(minutes=20), lease_expires_at=now+timedelta(seconds=30))
        waiting = CrawlJob(source_id=source.id, batch_id=batch, status="WAITING",
                           created_at=running.created_at)
        db.add_all([running, waiting])
        db.flush()
        assert queue_issues(db, now=now) == []
        running.lease_expires_at = now-timedelta(seconds=1)
        db.flush()
        assert queue_issues(db, now=now) == ["QUEUE_LEASE_EXPIRED"]
        running.status = "FAILED"
        running.finished_at = now
        db.flush()
        assert queue_issues(db, now=now) == []
        assert queue_issues(db, now=now+timedelta(minutes=6)) == ["QUEUE_NOT_PROGRESSING"]
        monkeypatch.setenv("OIP_COLLECTION_EMERGENCY_STOP", "true")
        assert queue_issues(db, now=now+timedelta(minutes=6)) == []


def test_socks_greeting_carries_no_destination(monkeypatch):
    from io import BytesIO
    from unittest.mock import MagicMock

    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.makefile.return_value = BytesIO(b"\x05\x00")
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr("app.collector.monitor.socket.create_connection", connect)
    assert socks_ready()
    connect.assert_called_once_with(("tor", 9050), timeout=3)
    connection.sendall.assert_called_once_with(b"\x05\x01\x00")
