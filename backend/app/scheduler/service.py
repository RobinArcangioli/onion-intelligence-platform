"""Governed UTC scheduling: no network, no Tor, no automatic retry of failed jobs.

Only a separately started scheduler with explicit OIP_SCHEDULER_ENABLED=true,
OIP_MANUAL_COLLECTION_ENABLED=true, and explicit ADMIN-approved per-source rows
can enqueue a pending job. Every due decision is persisted.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.collector.policy import (admission_lock, emergency_active, pending_full,
                                  read_policy, source_restriction)
from app.models import AuditLog, CrawlJob, OnionSource, SourceSchedule, ScheduleDecision
from app.security.onion import canonical_onion_page


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def scheduler_authorized() -> bool:
    # Explicitly require BOTH flags. Production API keeps manual collections off.
    for name in ("OIP_SCHEDULER_ENABLED", "OIP_MANUAL_COLLECTION_ENABLED"):
        value = os.getenv(name, "false").strip().lower()
        if value not in ("true", "false"):
            raise ValueError(f"Invalid {name}")
        if value != "true":
            return False
    return not emergency_active(read_policy())


def source_allowed(source: OnionSource | None) -> bool:
    if source is None or not (source.is_active and source.collection_enabled and
                                  source.approved_for_collection and source.deleted_at is None):
        return False
    try:
        return canonical_onion_page(source.canonical_url) == source.canonical_url
    except ValueError:
        return False


def window_open(schedule: SourceSchedule, now: datetime) -> bool:
    return schedule.window_start_hour <= now.hour < schedule.window_end_hour


def next_window_start(schedule: SourceSchedule, now: datetime) -> datetime:
    opening = now.replace(hour=schedule.window_start_hour, minute=0, second=0, microsecond=0)
    return opening if opening > now else opening + timedelta(days=1)


def dispatch_due(factory: sessionmaker[Session], *, now: datetime | None = None, max_sources: int = 100) -> dict[str, int]:
    """Process up to 100 due rows, committing one source at a time.

    Lock order: global advisory lock -> source row -> schedule row, matching
    manual admission. Re-check after locks; increments occur in same transaction.
    PostgreSQL transaction lock is REQUIRED for multi-instance dispatch safety.
    SQLite supports offline functional tests only.
    """
    if not 1 <= max_sources <= 100:
        raise ValueError("max_sources must be 1..100")
    if not scheduler_authorized():
        return {"DISABLED": 1}
    now = utc(now or datetime.now(timezone.utc))
    with factory() as db:
        ids = db.scalars(select(SourceSchedule.source_id)
                         .where(SourceSchedule.enabled.is_(True), SourceSchedule.next_run_at <= now)
                         .order_by(SourceSchedule.next_run_at, SourceSchedule.source_id)
                         .limit(max_sources)).all()
    counts: dict[str, int] = {}
    for source_id in ids:
        # Check at each source boundary, not only once per tick.
        if not scheduler_authorized():
            counts["HALTED"] = 1
            break
        with factory() as db:
            admission_lock(db)
            source = db.scalar(select(OnionSource).where(OnionSource.id == source_id).with_for_update())
            schedule = db.scalar(select(SourceSchedule).where(SourceSchedule.source_id == source_id).with_for_update())
            if schedule is None or not schedule.enabled or utc(schedule.next_run_at) > now:
                db.rollback()
                continue
            decision = ""
            job_id = None
            if not source_allowed(source):
                schedule.enabled = False  # Explicit ADMIN re-approval is required.
                decision = "SOURCE_DISABLED"
            elif utc(schedule.expires_at) <= now:
                schedule.enabled = False
                decision = "APPROVAL_EXPIRED"
            elif not window_open(schedule, now):
                decision = "OUTSIDE_WINDOW"
            else:
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                count = db.scalar(select(func.count(ScheduleDecision.id)).where(
                    ScheduleDecision.source_id == source_id,
                    ScheduleDecision.decision == "ENQUEUED",
                    ScheduleDecision.created_at >= start,
                    ScheduleDecision.created_at < start + timedelta(days=1),
                )) or 0
                active = db.scalar(select(CrawlJob.id).where(
                    CrawlJob.source_id == source_id, CrawlJob.status.in_(("PENDING", "RUNNING", "WAITING"))))
                policy = read_policy()
                if count >= schedule.daily_budget:
                    decision = "DAILY_BUDGET"
                elif active is not None:
                    decision = "ACTIVE_JOB"
                elif source_restriction(db, source_id, policy, now=now):
                    decision = "SOURCE_RESTRICTED"
                elif pending_full(db, policy):
                    decision = "GLOBAL_QUEUE_FULL"
                else:
                    job = CrawlJob(source_id=source_id, status="PENDING", created_at=now)
                    db.add(job)
                    db.flush()
                    job_id = job.id
                    decision = "ENQUEUED"
            if decision == "OUTSIDE_WINDOW":
                schedule.next_run_at = next_window_start(schedule, now)
            elif decision == "DAILY_BUDGET":
                tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                opening = tomorrow.replace(hour=schedule.window_start_hour)
                schedule.next_run_at = opening
            else:
                schedule.next_run_at = now + timedelta(minutes=schedule.interval_minutes)
            db.add(ScheduleDecision(source_id=source_id, job_id=job_id, decision=decision,
                                    approval_reference=schedule.approval_reference,
                                    authorization_expires_at=schedule.expires_at, created_at=now))
            db.add(AuditLog(actor="oip_scheduler", action="schedule.dispatch", entity_type="onion_source",
                            entity_id=source_id, details=json.dumps({"decision": decision,
                                                                      "job_id": str(job_id) if job_id else None})))
            try:
                db.commit()
            except IntegrityError:
                # A DB constraint failing never authorizes a duplicate job.
                db.rollback()
                raise
            counts[decision] = counts.get(decision, 0) + 1
    return counts
