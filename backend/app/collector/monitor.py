"""Read-only worker checks. Never claim a job or send a SOCKS destination."""
from datetime import datetime, timezone
import os
import socket
import sys
import time
from urllib.parse import urlsplit

from sqlalchemy import create_engine, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.collector.policy import _to_utc, eligible_jobs, emergency_active, read_policy, running_full
from app.collector.transport import SOCKS_PROXY
from app.collector.worker import WORKER_PULSE, WORKER_PULSE_MAX_AGE
from app.models import CrawlJob

MAX_ELIGIBLE_WAIT_SECONDS = 300


def queue_issues(db: Session, *, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    policy = read_policy()
    stale = db.scalar(select(CrawlJob.id).where(
        CrawlJob.status == "RUNNING",
        or_(CrawlJob.lease_expires_at.is_(None), CrawlJob.lease_expires_at <= now),
    ).limit(1))
    issues = ["QUEUE_LEASE_EXPIRED"] if stale else []
    if emergency_active(policy) or running_full(db, policy):
        return issues
    previous = aliased(CrawlJob)
    last_batch_finish = (select(func.max(previous.finished_at))
                         .where(previous.batch_id == CrawlJob.batch_id,
                                previous.source_id == CrawlJob.source_id,
                                previous.status.in_(("COMPLETED", "FAILED")))
                         .correlate(CrawlJob).scalar_subquery())
    for status, created, batch_finished in db.execute(
        select(CrawlJob.status, CrawlJob.created_at, last_batch_finish).where(eligible_jobs())
    ):
        eligible_at = _to_utc(created)
        if status == "WAITING" and batch_finished:
            eligible_at = max(eligible_at, _to_utc(batch_finished))
        if (now - eligible_at).total_seconds() >= MAX_ELIGIBLE_WAIT_SECONDS:
            issues.append("QUEUE_NOT_PROGRESSING")
            break
    return issues


def socks_ready() -> bool:
    proxy = urlsplit(SOCKS_PROXY)
    try:
        with socket.create_connection((proxy.hostname, proxy.port), timeout=3) as sock:
            sock.sendall(b"\x05\x01\x00")
            with sock.makefile("rb") as stream:
                return stream.read(2) == b"\x05\x00"
    except OSError:
        return False


def main() -> int:
    try:
        paused = emergency_active(read_policy())
        pulse_age = time.time() - WORKER_PULSE.stat().st_mtime if WORKER_PULSE.exists() else float("inf")
        if not paused and not 0 <= pulse_age <= WORKER_PULSE_MAX_AGE:
            print("WORKER_PULSE_STALE")
        if not paused and not socks_ready():
            print("TOR_PROXY_UNAVAILABLE")
        engine = create_engine(os.environ["OIP_DATABASE_URL"], connect_args={
            "connect_timeout": 3, "options": "-c statement_timeout=3000",
        })
        try:
            with Session(engine) as db:
                for issue in queue_issues(db):
                    print(issue)
        finally:
            engine.dispose()
        if paused:
            print("COLLECTION_PAUSED")
    except Exception:
        print("WORKER_CHECK_UNAVAILABLE")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
