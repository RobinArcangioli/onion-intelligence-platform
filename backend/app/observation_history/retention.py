"""Non-destructive retention impact analysis over existing minimal metadata.

Counts are *rows*, not distinct observations: several derivatives can refer to
one observation. Report snapshots and free-text audit details are deliberately
NOT treated as safe to delete, even when structured references count zero.
"""
from datetime import datetime
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (Alert, AuditLog, ClassificationResult, KeywordMatch,
                        Report, SourceObservation, ThreatIndicator, IocCandidate)


def impact_preview(db: Session, *, cutoff: datetime,
                   older_than_days: int, source_id: uuid.UUID | None = None) -> dict:
    criteria = [SourceObservation.created_at < cutoff]
    if source_id is not None:
        criteria.append(SourceObservation.source_id == source_id)
    # A SQL subquery avoids materializing observation UUIDs in Python or logs.
    candidate_ids = select(SourceObservation.id).where(*criteria)
    counts = {}
    for key, model in (
        ("keyword_matches", KeywordMatch),
        ("classifications", ClassificationResult),
        ("threat_indicators", ThreatIndicator),
        ("ioc_candidates", IocCandidate),
        ("alerts", Alert),
    ):
        counts[key] = db.scalar(select(func.count(model.id)).where(
            model.observation_id.in_(candidate_ids))) or 0
    # The audit log is append-only. entity_id is not an enforced FK; matching
    # UUIDs are a lower bound, and references in JSON details are not searched.
    counts["audit_entity_id_matches"] = db.scalar(select(func.count(AuditLog.id)).where(
        AuditLog.entity_id.in_(candidate_ids))) or 0
    reports = db.scalar(select(func.count(Report.id))) or 0
    observations = db.scalar(select(func.count(SourceObservation.id)).where(*criteria)) or 0
    return {
        "older_than_days": older_than_days,
        "cutoff": cutoff.isoformat(),
        "source_id": str(source_id) if source_id is not None else None,
        "observation_count": observations,
        "dependent_row_counts": counts,
        "report_snapshots_not_resolved": reports,
        "dry_run": True,
        "deletion_enabled": False,
        "safe_to_purge": False,
        "blockers": ["NO_APPROVED_PURGE_POLICY", "REPORT_SNAPSHOT_REFERENCES_NOT_ANALYZED",
                     "AUDIT_DETAILS_REFERENCES_NOT_ANALYZED", "OFFSITE_RESTORE_REQUIRED"],
        "note": "Dependent counts may overlap; they are not unique observations. "
                "No records are deleted. Reports and audit details may contain additional "
                "references not discoverable through foreign keys.",
    }
