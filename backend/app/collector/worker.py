"""Opt-in worker for manual UI jobs. Never auto-schedules or visits discovered URLs.

Run only from the isolated queue_worker Compose service. Queue polling is local DB
I/O; only claimed approved jobs make a single Tor fetch via the shared runner.
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.collector.runner import NotAuthorizedError, _allowed, collect_one
from app.models import AuditLog, CrawlJob, OnionSource
from app.security.onion import canonical_onion_root


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(db: Session, job: CrawlJob, action: str) -> None:
    db.add(AuditLog(actor="tor_queue_worker", action=action,
                    entity_type="onion_source", entity_id=job.source_id,
                    details=json.dumps({"job_id": str(job.id)})))


def claim_one(factory: sessionmaker[Session]) -> tuple[UUID, UUID] | None:
    """Atomic claim with PostgreSQL SKIP LOCKED; fail closed before any network."""
    with factory() as db:
        job = db.scalar(select(CrawlJob).where(CrawlJob.status == "PENDING")
                        .order_by(CrawlJob.created_at, CrawlJob.id)
                        .with_for_update(skip_locked=True).limit(1))
        if job is None:
            return None
        source = db.scalar(select(OnionSource).where(OnionSource.id == job.source_id).with_for_update())
        allowed = _allowed(source)
        if allowed:
            try:
                allowed = canonical_onion_root(source.canonical_url) == source.canonical_url
            except ValueError:
                allowed = False
        if not allowed:
            job.status = "FAILED"
            job.error_code = "AUTHORIZATION_REVOKED"
            job.finished_at = _now()
            _audit(db, job, "collection.rejected")
            db.commit()
            return None
        job.status = "RUNNING"
        job.started_at = _now()
        _audit(db, job, "collection.start")
        ids = job.id, job.source_id
        db.commit()
        return ids


def fail_claimed(factory: sessionmaker[Session], job_id: UUID) -> None:
    """Generic failure codes; never persist errors, URLs, HTML, or tracebacks."""
    with factory() as db:
        job = db.scalar(select(CrawlJob).where(CrawlJob.id == job_id).with_for_update())
        if job is not None and job.status == "RUNNING":
            job.status = "FAILED"
            job.error_code = "COLLECTION_FAILED"
            job.finished_at = _now()
            _audit(db, job, "collection.failed")
            db.commit()


async def process_one(factory: sessionmaker[Session], *, fetcher=None) -> bool:
    claimed = claim_one(factory)
    if claimed is None:
        return False
    job_id, source_id = claimed
    try:
        kw = {} if fetcher is None else {"fetcher": fetcher}
        _, status = await collect_one(source_id, factory, existing_job_id=job_id, **kw)
    except Exception:
        fail_claimed(factory, job_id)
        status = "FAILED"
    print(f"job_id={job_id} status={status}", flush=True)
    return True


def recover_stale(factory: sessionmaker[Session], *, minutes: int = 60) -> int:
    """Operator-only crash recovery. Stop worker first; no retry and no Tor fetch."""
    cutoff = _now() - timedelta(minutes=minutes)
    with factory() as db:
        jobs = db.scalars(select(CrawlJob).where(
            CrawlJob.status == "RUNNING", CrawlJob.started_at < cutoff,
        ).with_for_update(skip_locked=True)).all()
        for job in jobs:
            job.status = "FAILED"
            job.error_code = "WORKER_INTERRUPTED"
            job.finished_at = _now()
            _audit(db, job, "collection.abandoned")
        db.commit()
        return len(jobs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Process only explicitly queued Onion collection jobs")
    parser.add_argument("--once", action="store_true", help="Handle at most one pending job")
    parser.add_argument("--recover-stale", action="store_true",
                        help="After stopping the worker, mark >60-minute RUNNING jobs failed (no retry)")
    args = parser.parse_args()
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
        if args.recover_stale:
            count = recover_stale(factory)
            print(f"reconciled_jobs={count}")
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
