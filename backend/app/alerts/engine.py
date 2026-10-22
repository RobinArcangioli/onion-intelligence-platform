"""Observation-linked, deduplicated alerts without excerpts or watchlist phrases.

A replay of the same observed content cannot create additional alerts. A
later modified page can create a new alert for the same signal; reopening
an old alert is always a separate, explicit operator decision (not automatic).
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Alert, ClassificationResult, KeywordMatch, SourceObservation, ThreatIndicator

RELEVANCE_ALERT_THRESHOLD = 70
MAX_ALERTS_PER_OBSERVATION = 128


@dataclass(frozen=True)
class AlertSignal:
    event_type: str
    signal_code: str
    stable_key: str
    priority: str
    verification_status: str


def _fingerprint(observation: SourceObservation, signal: AlertSignal) -> str:
    raw = "|".join((str(observation.source_id), observation.text_sha256,
                    signal.event_type, signal.stable_key))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def observation_signals(db: Session, observation: SourceObservation) -> list[AlertSignal]:
    categories = db.scalars(select(ClassificationResult).where(
        ClassificationResult.observation_id == observation.id)).all()
    # If content was quarantined, only ask for human review; suppress all
    # other signal types and never include metadata from the sensitive page.
    if any(c.category == "SUSPECTED_CHILD_EXPLOITATION" for c in categories):
        return [AlertSignal("SENSITIVE_REVIEW", "REVIEW_REQUIRED", "sensitive_review",
                            "HIGH", "UNVERIFIED_REPORT")]

    signals: list[AlertSignal] = []
    for match in db.scalars(select(KeywordMatch).where(
            KeywordMatch.observation_id == observation.id).order_by(KeywordMatch.rule_id)).all():
        signals.append(AlertSignal("WATCHLIST_MATCH", "KEYWORD_OCCURRENCE", str(match.rule_id),
                                   "MEDIUM", "OBSERVED_REFERENCE"))

    for indicator in db.scalars(select(ThreatIndicator).where(
            ThreatIndicator.observation_id == observation.id)
            .order_by(ThreatIndicator.indicator_type, ThreatIndicator.public_reference)).all():
        # Public references (CVE) are not compromised credentials or proof of harm.
        signals.append(AlertSignal("CTI_SIGNAL", indicator.indicator_type,
                                   f"{indicator.indicator_type}:{indicator.public_reference}",
                                   "MEDIUM" if indicator.verification_status == "OBSERVED_CLAIM" else "LOW",
                                   indicator.verification_status))

    if observation.change_status == "MODIFIED":
        signals.append(AlertSignal("CONTENT_CHANGED", "TEXT_FINGERPRINT_CHANGED", "changed",
                                   "LOW", "DIRECT_OBSERVATION"))
    if observation.relevance_score >= RELEVANCE_ALERT_THRESHOLD:
        signals.append(AlertSignal("RELEVANCE_THRESHOLD", "SCORE_AT_LEAST_70", "relevance_threshold",
                                   "MEDIUM", "HEURISTIC_SCORE"))
    # Keep claim/review and significant changes ahead of less actionable matches
    # if the bounded event quota is reached. Stable sorting preserves replay order.
    weights = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    kinds = {"CTI_SIGNAL": 0, "RELEVANCE_THRESHOLD": 1, "CONTENT_CHANGED": 2, "WATCHLIST_MATCH": 3}
    signals.sort(key=lambda x: (weights[x.priority], kinds.get(x.event_type, 9), x.stable_key))
    return signals[:MAX_ALERTS_PER_OBSERVATION]


def emit_observation_alerts(db: Session, observation: SourceObservation) -> int:
    """Flush dependent findings, then insert unique alerts in the same transaction.

    Savepoints handle racing identical fingerprints without rolling back a
    successful collection. This function never commits the outer transaction.
    """
    db.flush()
    created = 0
    for signal in observation_signals(db, observation):
        digest = _fingerprint(observation, signal)
        if db.scalar(select(Alert.id).where(Alert.fingerprint == digest)) is not None:
            continue
        try:
            with db.begin_nested():
                db.add(Alert(
                    source_id=observation.source_id, observation_id=observation.id,
                    fingerprint=digest, event_type=signal.event_type, signal_code=signal.signal_code,
                    priority=signal.priority, verification_status=signal.verification_status,
                    relevance_score=observation.relevance_score,
                ))
                db.flush()
                created += 1
        except IntegrityError:
            # Concurrent collection / retry already inserted this fingerprint.
            pass
    return created
