"""Conservative DB-backed admission controls; never performs network I/O.

No implicit requeue, retry, scheduler, or Onion discovery is introduced here.
Limits are intentionally modest; the hosted pilot keeps collection disabled.
"""
import os
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import CrawlJob

# PostgreSQL transaction-scoped advisory mutex serializes global queue counters.
# It is not a substitute for the per-source row lock and unique active-job index.
_ADMISSION_LOCK_ID = 7298314602
_NETWORK_FAILURES = frozenset({"TOR_NETWORK_ERROR", "FETCH_TIMEOUT", "COLLECTION_FAILED"})


def _bounded_int(name: str, default: int, low: int, high: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


@dataclass(frozen=True)
class CollectionPolicy:
    source_cooldown_seconds: int = 300
    max_pending: int = 25
    max_running: int = 2
    circuit_failures: int = 3
    circuit_open_seconds: int = 3600
    emergency_stop: bool = False


def read_policy() -> CollectionPolicy:
    flag = os.getenv("OIP_COLLECTION_EMERGENCY_STOP", "false").strip().lower()
    if flag not in ("true", "false"):
        raise ValueError("OIP_COLLECTION_EMERGENCY_STOP must be true or false")
    return CollectionPolicy(
        source_cooldown_seconds=_bounded_int("OIP_COLLECTION_SOURCE_COOLDOWN_SECONDS", 300, 0, 86400),
        max_pending=_bounded_int("OIP_COLLECTION_MAX_PENDING", 25, 1, 500),
        max_running=_bounded_int("OIP_COLLECTION_MAX_RUNNING", 2, 1, 16),
        circuit_failures=_bounded_int("OIP_COLLECTION_CIRCUIT_FAILURES", 3, 2, 10),
        circuit_open_seconds=_bounded_int("OIP_COLLECTION_CIRCUIT_OPEN_SECONDS", 3600, 60, 86400),
        emergency_stop=flag == "true",
    )


def admission_lock(db: Session) -> None:
    """Acquire a single PG transaction lock before all global counter checks.

    SQLite's concurrency model is different; it only powers offline tests.
    Production multiworker guarantees require the PostgreSQL concurrency test.
    """
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADMISSION_LOCK_ID})


def pending_full(db: Session, policy: CollectionPolicy) -> bool:
    return (db.scalar(select(func.count()).select_from(CrawlJob).where(CrawlJob.status == "PENDING")) or 0) >= policy.max_pending


def running_full(db: Session, policy: CollectionPolicy) -> bool:
    return (db.scalar(select(func.count()).select_from(CrawlJob).where(CrawlJob.status == "RUNNING")) or 0) >= policy.max_running


def _to_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def source_restriction(db: Session, source_id, policy: CollectionPolicy, *, now: datetime | None = None) -> str | None:
    """Bounded manual quota plus time-limited circuit breaker for repeated failures.

    Circuit opens for one hour after N consecutive network failures (or a
    configured interval). Only a NEW manual enqueue after expiry may proceed.
    """
    now = now or datetime.now(timezone.utc)
    latest = db.scalars(select(CrawlJob).where(CrawlJob.source_id == source_id)
                        .order_by(CrawlJob.created_at.desc(), CrawlJob.id.desc())
                        .limit(max(1, policy.circuit_failures))).all()
    if latest and policy.source_cooldown_seconds:
        created = latest[0].created_at
        if created and _to_utc(created) + timedelta(seconds=policy.source_cooldown_seconds) > now:
            return "SOURCE_COOLDOWN"
    # PENDING/RUNNING are checked separately by the active job constraint.
    if len(latest) >= policy.circuit_failures and all(
        job.status == "FAILED" and job.error_code in _NETWORK_FAILURES for job in latest
    ):
        finish = latest[0].finished_at
        if finish and _to_utc(finish) + timedelta(seconds=policy.circuit_open_seconds) > now:
            return "CIRCUIT_OPEN"
    return None


def emergency_active(policy: CollectionPolicy) -> bool:
    """Check both restart-based global env gate and live local worker sentinel.

    The sentinel is container-local unless operators explicitly mount a shared
    control path; for a cross-service shutdown, stop workers and disable API
    enqueue separately. A missing file does not loosen the env stop.
    """
    filename = os.getenv("OIP_COLLECTION_KILL_FILE", "/tmp/oip-collection.disabled")
    if not filename.startswith("/") or len(filename) > 512:
        raise ValueError("OIP_COLLECTION_KILL_FILE must be an absolute path")
    return policy.emergency_stop or Path(filename).exists()
