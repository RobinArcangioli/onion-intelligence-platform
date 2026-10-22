"""Build immutable reports from codes and counters only.

Never include original HTML, text, titles, descriptions, Onion URLs,
watchlist phrases, audit reasons, or other content in a report snapshot.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models import Alert, ClassificationResult, DiscoveredOnion, SourceObservation, ThreatIndicator

REPORT_ENTITIES = {
    "observations": (SourceObservation, "created_at"),
    "discoveries": (DiscoveredOnion, "first_seen_at"),
    "classifications": (ClassificationResult, "created_at"),
    "indicators": (ThreatIndicator, "created_at"),
    "alerts": (Alert, "created_at"),
}
REPORT_DISCLAIMER = (
    "Observed source content and automated classifications are not evidence of a verified incident. "
    "A claim is unverified unless independently corroborated."
)
CSV_COLUMNS = ("record_type", "id", "source_id", "observation_id", "code",
               "score", "confidence", "verification_status", "status", "occurred_at")


def _row_payload(kind: str, row: Any, at: datetime) -> dict:
    base: dict[str, Any] = {
        "record_type": kind,
        "id": str(row.id),
        "source_id": str(row.source_id),
        "observation_id": str(row.observation_id) if getattr(row, "observation_id", None) else "",
        "code": "",
        "score": "",
        "confidence": "",
        "verification_status": "",
        "status": "",
        "occurred_at": at.isoformat(),
    }
    if kind == "observations":
        base.update(code=row.change_status, score=row.relevance_score,
                    verification_status="DIRECT_OBSERVATION")
    elif kind == "discoveries":
        # Omit target_url and any origin content.
        base.update(code="DISCOVERY_" + row.status,
                    verification_status="UNVERIFIED_CANDIDATE", status=row.status)
    elif kind == "classifications":
        base.update(code=row.category, confidence=row.confidence,
                    verification_status=row.review_status, status=row.review_status)
    elif kind == "indicators":
        base.update(code=row.indicator_type, confidence=row.confidence,
                    verification_status=row.verification_status)
    elif kind == "alerts":
        base.update(code=row.event_type + ":" + row.signal_code,
                    score=row.relevance_score, verification_status=row.verification_status, status=row.status)
    return base


def build_snapshot(db: Session, *, start: datetime, end: datetime,
                   source_id: Any, max_rows: int) -> dict:
    """Queries and snapshot are bounded. Persisting is responsibility of caller."""
    totals: dict[str, int] = {}
    rows: dict[str, list[dict]] = {}
    truncated: list[str] = []
    for kind, (model, field) in REPORT_ENTITIES.items():
        timestamp = getattr(model, field)
        clauses = [timestamp >= start, timestamp < end]
        if source_id is not None:
            clauses.append(model.source_id == source_id)
        total = db.scalar(select(func.count()).select_from(model).where(*clauses)) or 0
        found = db.scalars(select(model).where(*clauses)
                           .order_by(timestamp.desc(), model.id.desc()).limit(max_rows)).all()
        totals[kind] = total
        rows[kind] = [_row_payload(kind, row, getattr(row, field)) for row in found]
        if total > len(found):
            truncated.append(kind)
    return {
        "schema_version": "1",
        "disclaimer": REPORT_DISCLAIMER,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "source_id": str(source_id) if source_id else None,
        "row_limit_per_type": max_rows,
        "totals": totals,
        "truncated_types": truncated,
        "records": rows,
    }


def export_csv(snapshot: dict) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\r\n",
                            extrasaction="ignore")
    writer.writeheader()
    for kind in REPORT_ENTITIES:
        for row in snapshot["records"].get(kind, []):
            writer.writerow(row)
    return buffer.getvalue()
