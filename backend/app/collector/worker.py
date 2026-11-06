"""Opt-in, single-fetch queue worker: no scheduler, no automatic retries.

M2-B: PostgreSQL SKIP LOCKED claim, renewable lease and per-claim fencing token.
Expired or interrupted work is NEVER automatically re-enqueued. Recovery is
an explicit administrative DB-only action after stopping every worker.
"""
import argparse
import asyncio
import contextlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import create_engine, func, or_, select, update
from sqlalchemy.orm import Session, aliased, sessionmaker

from app.collector.runner import collect_one, job_target
from app.collector.policy import admission_lock, emergency_active, read_policy, running_full
from app.models import AuditLog, CrawlJob, OnionSource, SourceSchedule, ScheduleDecision

LEASE_SECONDS = 180   # Must be greater than the fetch timeout (120 s).
HEARTBEAT_SECONDS = 20


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(db: Session, job: CrawlJob, action: str) -> None:
    db.add(AuditLog(actor="tor_queue_worker", action=action,
                    entity_type="onion_source", entity_id=job.source_id,
                    details=json.dumps({"job_id": str(job.id)})))


def claim_one(factory: sessionmaker[Session]) -> tuple[UUID, UUID, UUID] | None:
    """Atomic claim; the fencing token is secret and never leaves worker memory.

    On PostgreSQL the row lock prevents duplicate claims; the partial unique
    index also prevents concurrent active jobs for the same source.
    """
    if emergency_active(read_policy()):
        return None
    with factory() as db:
        admission_lock(db)
        if running_full(db, read_policy()):
            db.rollback()
            return None
        active = aliased(CrawlJob)
        source_busy = select(active.id).where(
            active.source_id == CrawlJob.source_id, active.status.in_(("PENDING", "RUNNING")),
        ).exists()
        job = db.scalar(select(CrawlJob).where(or_(
            CrawlJob.status == "PENDING", (CrawlJob.status == "WAITING") & ~source_busy,
        ))
                        .order_by(CrawlJob.created_at, CrawlJob.id)
                        .with_for_update(skip_locked=True).limit(1))
        if job is None:
            return None
        source = db.scalar(select(OnionSource).where(OnionSource.id == job.source_id).with_for_update())
        allowed = job_target(db, source, job) is not None
        # A previously queued SCHEDULED job is still subject to explicit
        # schedule approval when the worker actually claims it. Manual jobs
        # have no ScheduleDecision and are unaffected by a schedule pause.
        scheduled = db.scalar(select(ScheduleDecision).where(
            ScheduleDecision.job_id == job.id, ScheduleDecision.decision == "ENQUEUED"))
        if scheduled is not None:
            schedule = db.get(SourceSchedule, job.source_id)
            if schedule is None or not schedule.enabled or (
                schedule.expires_at is None or
                (schedule.expires_at.replace(tzinfo=timezone.utc)
                 if schedule.expires_at.tzinfo is None else schedule.expires_at) <= _now()
            ):
                job.status = "FAILED"
                job.error_code = "SCHEDULE_AUTHORIZATION_EXPIRED"
                job.finished_at = _now()
                _audit(db, job, "schedule.rejected_at_claim")
                db.commit()
                return None
        if not allowed:
            job.status = "FAILED"
            job.error_code = "AUTHORIZATION_REVOKED"
            job.finished_at = _now()
            _audit(db, job, "collection.rejected")
            db.commit()
            return None
        now = _now()
        token = uuid.uuid4()
        job.status = "RUNNING"
        job.started_at = now
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        job.lease_token = token
        _audit(db, job, "collection.start")
        ids = job.id, job.source_id, token
        db.commit()
        return ids


def renew_lease(factory: sessionmaker[Session], job_id: UUID, token: UUID) -> bool:
    """Compare-and-swap renewal: no resurrection after expiry or reconciliation."""
    now = _now()
    with factory() as db:
        updated = db.execute(update(CrawlJob).where(
            CrawlJob.id == job_id,
            CrawlJob.status == "RUNNING",
            CrawlJob.lease_token == token,
            CrawlJob.lease_expires_at > now,
        ).values(heartbeat_at=now, lease_expires_at=now + timedelta(seconds=LEASE_SECONDS)))
        db.commit()
        return updated.rowcount == 1


def fail_claimed(factory: sessionmaker[Session], job_id: UUID, token: UUID) -> bool:
    """Only the current, unexpired lease holder may mark its attempt failed."""
    with factory() as db:
        job = db.scalar(select(CrawlJob).where(
            CrawlJob.id == job_id, CrawlJob.status == "RUNNING",
            CrawlJob.lease_token == token, CrawlJob.lease_expires_at > _now(),
        ).with_for_update())
        if job is None:
            return False
        job.status = "FAILED"
        job.error_code = "COLLECTION_FAILED"
        job.finished_at = _now()
        job.lease_token = None
        job.lease_expires_at = None
        _audit(db, job, "collection.failed")
        db.commit()
        return True


async def _heartbeat(factory: sessionmaker[Session], job_id: UUID, token: UUID,
                     processing: asyncio.Task) -> None:
    """Keep lease alive during network I/O and analysis; cancel on lost ownership.

    A transient DB exception does not itself grant authority: finalization
    always checks the current lease in the DB. A missed renewal ultimately
    expires. Cancellation does not start another fetch.
    """
    while not processing.done():
        await asyncio.sleep(HEARTBEAT_SECONDS)
        if processing.done():
            break
        # Runtime operator stop: set the flag, recreate containers if using
        # env-based configuration, or stop the worker service immediately.
        try:
            halted = emergency_active(read_policy())
        except ValueError:
            halted = True  # Invalid stop configuration fails closed.
        if halted:
            processing.cancel()
            return
        try:
            live = await asyncio.to_thread(renew_lease, factory, job_id, token)
        except Exception:
            # A DB outage cannot authorize a stale write or a retry.
            continue
        if not live:
            processing.cancel()
            return


async def process_one(factory: sessionmaker[Session], *, fetcher=None) -> bool:
    claimed = claim_one(factory)
    if claimed is None:
        return False
    job_id, source_id, token = claimed
    kw = {} if fetcher is None else {"fetcher": fetcher}
    processing = asyncio.create_task(collect_one(
        source_id, factory, existing_job_id=job_id, lease_token=token, **kw))
    heartbeat = asyncio.create_task(_heartbeat(factory, job_id, token, processing))
    try:
        try:
            _, status = await processing
        except asyncio.CancelledError:
            # Terminating a worker cannot silently commit any observation.
            processing.cancel()
            raise
        except Exception:
            fail_claimed(factory, job_id, token)
            status = "FAILED"
        print(f"job_id={job_id} status={status}", flush=True)
        return True
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat
        if not processing.done():
            processing.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await processing


def _stale_cutoff(minutes: int) -> datetime:
    if not 1 <= minutes <= 10080:
        raise ValueError("stale window must be 1..10080 minutes")
    return _now() - timedelta(minutes=minutes)


def _stale_query(cutoff: datetime):
    """Age threshold PLUS lease expiry: a slow *live* worker stays protected.

    Pre-migration RUNNING jobs have no lease; they need manual reconciliation.
    """
    return (CrawlJob.status == "RUNNING", CrawlJob.started_at < cutoff,
            or_(CrawlJob.lease_expires_at.is_(None), CrawlJob.lease_expires_at < _now()))


def inspect_stale(factory: sessionmaker[Session], *, minutes: int = 60) -> int:
    """Read-only count. Does not acquire locks or issue network requests."""
    cutoff = _stale_cutoff(minutes)
    with factory() as db:
        return db.scalar(select(func.count(CrawlJob.id)).where(*_stale_query(cutoff))) or 0


def recover_stale(factory: sessionmaker[Session], *, minutes: int = 60) -> int:
    """OFFLINE ONLY: operator stopped all collectors, then marks stale jobs FAILED.

    Old worker tokens are invalidated. Never requeues or calls Tor.
    """
    cutoff = _stale_cutoff(minutes)
    with factory() as db:
        jobs = db.scalars(select(CrawlJob).where(*_stale_query(cutoff))
                          .with_for_update(skip_locked=True)).all()
        for job in jobs:
            job.status = "FAILED"
            job.error_code = "WORKER_INTERRUPTED"
            job.finished_at = _now()
            job.lease_token = None
            job.lease_expires_at = None
            _audit(db, job, "collection.abandoned")
        db.commit()
        return len(jobs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Process only explicitly queued Onion collection jobs")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--once", action="store_true", help="Handle at most one pending job")
    action.add_argument("--inspect-stale", action="store_true", help="Read-only count of expired/old RUNNING jobs")
    action.add_argument("--recover-stale", action="store_true", help="Close expired/old jobs after stopping all workers")
    parser.add_argument("--stale-minutes", type=int, default=60,
                        help="Minimum age in minutes, AND lease expired (1..10080; default 60)")
    parser.add_argument("--confirm-worker-stopped", action="store_true",
                        help="Attest that queue_worker and other collectors are stopped")
    args = parser.parse_args()
    if not 1 <= args.stale_minutes <= 10080:
        parser.error("--stale-minutes must be 1..10080")
    if args.confirm_worker_stopped and not args.recover_stale:
        parser.error("--confirm-worker-stopped only applies to --recover-stale")
    if args.recover_stale and not args.confirm_worker_stopped:
        parser.error("--recover-stale requires --confirm-worker-stopped")
    # Inspection and reconciliation do not require Tor and must not enable it.
    # A global emergency stop prevents processing but never blocks inspection.
    if not (args.inspect_stale or args.recover_stale):
        if emergency_active(read_policy()):
            print("Worker disabled: emergency stop is active", file=sys.stderr)
            return 2
        if os.getenv("OIP_TOR_COLLECTION_ENABLED", "false").lower() != "true":
            print("Worker disabled: OIP_TOR_COLLECTION_ENABLED=true required", file=sys.stderr)
            return 2
    url = os.getenv("OIP_DATABASE_URL")
    if not url:
        print("OIP_DATABASE_URL required", file=sys.stderr)
        return 2
    engine = create_engine(url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        if args.inspect_stale:
            print(f"stale_running_jobs={inspect_stale(factory, minutes=args.stale_minutes)}")
            return 0
        if args.recover_stale:
            print(f"reconciled_jobs={recover_stale(factory, minutes=args.stale_minutes)}")
            return 0
        while True:
            handled = asyncio.run(process_one(factory))
            if args.once:
                break
            if not handled:
                time.sleep(3)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
