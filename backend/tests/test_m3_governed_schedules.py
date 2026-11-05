"""M3 opt-in scheduling: strictly local SQLite, synthetic Onion identifiers."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select

from app.models import AuditLog, CrawlJob, ScheduleDecision, SourceSchedule
from app.scheduler.service import dispatch_due
from tests.test_manual_queue_rc2 import LEGACY, REASON, create_role, registered, enable


def config(*, enabled=True, interval=60, budget=2, start=0, end=24, expiry=None):
    return {"enabled": enabled, "interval_minutes": interval, "daily_budget": budget,
            "window_start_hour": start, "window_end_hour": end,
            "expires_at": (expiry or datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
            "approval_reference": "Explicit owner authorization 2026",
            "reason": "Governed opt-in schedule approved"}


def prepare(client, root):
    sid = registered(client, root)
    enable(client, sid)
    return sid


def put(client, sid, **kwargs):
    return client.put(f"/api/v1/schedules/{sid}", headers=LEGACY, json=config(**kwargs))


def permit(monkeypatch):
    monkeypatch.setenv("OIP_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("OIP_MANUAL_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("OIP_COLLECTION_SOURCE_COOLDOWN_SECONDS", "0")


def test_no_schedule_by_default_and_admin_only(client, db_session_factory, valid_onion_url):
    sid = prepare(client, valid_onion_url)
    viewer = create_role(db_session_factory, "VIEWER")
    assert client.get(f"/api/v1/schedules/{sid}", headers=LEGACY).status_code == 404
    assert client.put(f"/api/v1/schedules/{sid}", json=config()).status_code == 401
    assert client.put(f"/api/v1/schedules/{sid}", headers=viewer, json=config()).status_code == 403
    assert client.get(f"/api/v1/schedules/{sid}/decisions", headers=viewer).status_code == 403
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceSchedule)) == 0


def test_only_explicit_valid_optin(client, valid_onion_url):
    sid = registered(client, valid_onion_url)
    assert put(client, sid).status_code == 409
    enable(client, sid)
    payload = config()
    payload.pop("enabled")
    assert client.put(f"/api/v1/schedules/{sid}", headers=LEGACY, json=payload).status_code == 422
    payload = config(expiry=datetime.now(timezone.utc) - timedelta(hours=1))
    assert client.put(f"/api/v1/schedules/{sid}", headers=LEGACY, json=payload).status_code == 422
    payload = config()
    payload["expires_at"] = "2026-12-01T00:00:00"  # Naive rejected.
    assert client.put(f"/api/v1/schedules/{sid}", headers=LEGACY, json=payload).status_code == 422
    payload = config()
    payload["approval_reference"] = "                "
    assert client.put(f"/api/v1/schedules/{sid}", headers=LEGACY, json=payload).status_code == 422
    payload = config(start=14, end=7)
    assert client.put(f"/api/v1/schedules/{sid}", headers=LEGACY, json=payload).status_code == 422
    assert put(client, sid).status_code == 200
    assert client.get(f"/api/v1/schedules/{sid}", headers=LEGACY).json()["enabled"] is True


def test_global_gates_default_off(client, db_session_factory, valid_onion_url, monkeypatch):
    sid = prepare(client, valid_onion_url)
    assert put(client, sid).status_code == 200
    monkeypatch.delenv("OIP_SCHEDULER_ENABLED", raising=False)
    monkeypatch.delenv("OIP_MANUAL_COLLECTION_ENABLED", raising=False)
    assert dispatch_due(db_session_factory) == {"DISABLED": 1}
    monkeypatch.setenv("OIP_SCHEDULER_ENABLED", "true")
    assert dispatch_due(db_session_factory) == {"DISABLED": 1}
    monkeypatch.setenv("OIP_MANUAL_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("OIP_COLLECTION_EMERGENCY_STOP", "true")
    assert dispatch_due(db_session_factory) == {"DISABLED": 1}
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(CrawlJob)) == 0


def test_due_enqueues_once_and_links_audit(client, db_session_factory, valid_onion_url, monkeypatch):
    sid = prepare(client, valid_onion_url)
    assert put(client, sid).status_code == 200
    permit(monkeypatch)
    assert dispatch_due(db_session_factory) == {"ENQUEUED": 1}
    assert dispatch_due(db_session_factory) == {}
    with db_session_factory() as db:
        job = db.scalar(select(CrawlJob))
        decision = db.scalar(select(ScheduleDecision))
        assert job.status == "PENDING" and job.id == decision.job_id
        assert decision.source_id == UUID(sid)
        assert decision.approval_reference == "Explicit owner authorization 2026"
        assert decision.authorization_expires_at is not None
        assert db.scalar(select(AuditLog).where(AuditLog.action == "schedule.dispatch")) is not None
    response = client.get(f"/api/v1/schedules/{sid}/decisions", headers=LEGACY)
    assert response.status_code == 200 and response.json()[0]["job_id"] == str(job.id)
    assert "lease_token" not in response.text


def test_expiration_pauses_no_job(client, db_session_factory, valid_onion_url, monkeypatch):
    sid = prepare(client, valid_onion_url)
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    assert put(client, sid, expiry=expires).status_code == 200
    permit(monkeypatch)
    assert dispatch_due(db_session_factory, now=expires + timedelta(seconds=1)) == {"APPROVAL_EXPIRED": 1}
    with db_session_factory() as db:
        assert db.get(SourceSchedule, UUID(sid)).enabled is False
        assert db.scalar(select(func.count()).select_from(CrawlJob)) == 0


def test_outside_window_never_queues(client, db_session_factory, valid_onion_url, monkeypatch):
    sid = prepare(client, valid_onion_url)
    assert put(client, sid, start=12, end=13).status_code == 200
    permit(monkeypatch)
    now = datetime.now(timezone.utc).replace(hour=7, minute=0, second=0, microsecond=0)
    with db_session_factory() as db:
        db.get(SourceSchedule, UUID(sid)).next_run_at = now - timedelta(minutes=1)
        db.commit()
    assert dispatch_due(db_session_factory, now=now) == {"OUTSIDE_WINDOW": 1}
    with db_session_factory() as db:
        assert db.get(SourceSchedule, UUID(sid)).next_run_at.hour == 12
        assert db.scalar(select(func.count()).select_from(CrawlJob)) == 0


def test_budget_respected_over_successive_due_slots(client, db_session_factory, valid_onion_url, monkeypatch):
    sid = prepare(client, valid_onion_url)
    assert put(client, sid, budget=1).status_code == 200
    permit(monkeypatch)
    assert dispatch_due(db_session_factory) == {"ENQUEUED": 1}
    with db_session_factory() as db:
        job = db.scalar(select(CrawlJob))
        job.status = "COMPLETED"
        schedule = db.get(SourceSchedule, UUID(sid))
        schedule.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert dispatch_due(db_session_factory) == {"DAILY_BUDGET": 1}
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(CrawlJob)) == 1


def test_active_job_prevents_second_dispatch(client, db_session_factory, valid_onion_url, monkeypatch):
    sid = prepare(client, valid_onion_url)
    assert put(client, sid).status_code == 200
    permit(monkeypatch)
    assert dispatch_due(db_session_factory) == {"ENQUEUED": 1}
    with db_session_factory() as db:
        db.get(SourceSchedule, UUID(sid)).next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert dispatch_due(db_session_factory) == {"ACTIVE_JOB": 1}


def test_revocation_pauses_and_never_resumes_implicitly(client, db_session_factory, valid_onion_url, monkeypatch):
    sid = prepare(client, valid_onion_url)
    assert put(client, sid).status_code == 200
    assert client.post(f"/api/v1/sources/{sid}/collection/disable", headers=LEGACY, json=REASON).status_code == 200
    permit(monkeypatch)
    assert dispatch_due(db_session_factory) == {}
    with db_session_factory() as db:
        assert db.get(SourceSchedule, UUID(sid)).enabled is False
    assert client.post(f"/api/v1/sources/{sid}/collection/enable", headers=LEGACY, json=REASON).status_code == 200
    assert dispatch_due(db_session_factory) == {}
    assert put(client, sid).status_code == 200
    assert client.post(f"/api/v1/sources/{sid}/revoke", headers=LEGACY, json=REASON).status_code == 200
    assert dispatch_due(db_session_factory) == {}


def test_manual_pause(client, db_session_factory, valid_onion_url, monkeypatch):
    sid = prepare(client, valid_onion_url)
    assert put(client, sid).status_code == 200
    res = client.post(f"/api/v1/schedules/{sid}/pause", headers=LEGACY, json=REASON)
    assert res.status_code == 200 and not res.json()["enabled"]
    permit(monkeypatch)
    assert dispatch_due(db_session_factory) == {}


def test_global_queue_full_is_logged_not_retried(client, db_session_factory, valid_onion_url, monkeypatch):
    import uuid
    from app.models import OnionSource
    sid = prepare(client, valid_onion_url)
    assert put(client, sid).status_code == 200
    permit(monkeypatch)
    monkeypatch.setenv("OIP_COLLECTION_MAX_PENDING", "1")
    with db_session_factory() as db:
        second = OnionSource(id=uuid.uuid4(),canonical_url='http://synthetic.onion/',name='synthetic',authorization_note='test')
        db.add(second)
        db.flush()
        db.add(CrawlJob(source_id=second.id, status="PENDING"))
        db.commit()
    assert dispatch_due(db_session_factory) == {"GLOBAL_QUEUE_FULL": 1}


def test_invalid_gate_fails_closed(monkeypatch, db_session_factory):
    import pytest
    monkeypatch.setenv("OIP_SCHEDULER_ENABLED", "sometimes")
    with pytest.raises(ValueError, match="OIP_SCHEDULER_ENABLED"):
        dispatch_due(db_session_factory)


def test_queued_schedule_pause_is_rechecked_on_worker_claim(client, db_session_factory, valid_onion_url, monkeypatch):
    from app.collector.worker import claim_one
    sid = prepare(client, valid_onion_url)
    assert put(client, sid).status_code == 200
    permit(monkeypatch)
    assert dispatch_due(db_session_factory) == {"ENQUEUED": 1}
    assert client.post(f"/api/v1/schedules/{sid}/pause", headers=LEGACY, json=REASON).status_code == 200
    assert claim_one(db_session_factory) is None
    with db_session_factory() as db:
        job = db.scalar(select(CrawlJob))
        assert job.status == "FAILED" and job.error_code == "SCHEDULE_AUTHORIZATION_EXPIRED"


def test_queued_schedule_expiry_blocks_claim(client, db_session_factory, valid_onion_url, monkeypatch):
    from app.collector.worker import claim_one
    sid = prepare(client, valid_onion_url)
    assert put(client, sid).status_code == 200
    permit(monkeypatch)
    assert dispatch_due(db_session_factory) == {"ENQUEUED": 1}
    with db_session_factory() as db:
        schedule = db.get(SourceSchedule, UUID(sid))
        schedule.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert claim_one(db_session_factory) is None
    with db_session_factory() as db:
        assert db.scalar(select(CrawlJob)).status == "FAILED"


def test_historical_authorization_snapshot_survives_schedule_edit(client, db_session_factory, valid_onion_url, monkeypatch):
    sid = prepare(client, valid_onion_url)
    assert put(client, sid).status_code == 200
    permit(monkeypatch)
    assert dispatch_due(db_session_factory) == {"ENQUEUED": 1}
    payload = config(enabled=False)
    payload["approval_reference"] = "A completely different approval reference"
    assert client.put(f"/api/v1/schedules/{sid}", headers=LEGACY, json=payload).status_code == 200
    with db_session_factory() as db:
        old = db.scalar(select(ScheduleDecision))
        assert old.approval_reference == "Explicit owner authorization 2026"
        assert db.get(SourceSchedule, UUID(sid)).approval_reference == "A completely different approval reference"
