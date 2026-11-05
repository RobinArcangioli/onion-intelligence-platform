"""Versioned, deterministic documentary *mention quality* rubric (not a threat score).

This module performs no enrichment, network access, persistence or attribution.
Acceptance confirms only an analyst's review of a mention. No automated
severity, exploitation likelihood, compromise probability or CVSS is inferred.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone

RUBRIC_VERSION = "M5C_MENTION_QUALITY_V1"


@dataclass(frozen=True)
class MentionQuality:
    score: int
    freshness: str
    age_days: int
    explanation_codes: tuple[str, ...]
    rubric_version: str = RUBRIC_VERSION


def mention_quality(*, confidence: int, review_status: str, observed_at: datetime,
                    as_of: datetime | None = None) -> MentionQuality:
    """Compute capped quality-of-documentation from *existing* source metadata.

    Confidence and analyst priority are distinct quantities. A review does not
    validate the truth of any reported activity; age is anchored to the original
    observation, NOT the latest review or API request.
    """
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    observed = observed_at.replace(tzinfo=timezone.utc) if observed_at.tzinfo is None else observed_at
    days = max(0, (now.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).days)
    score = max(0, min(100, int(confidence)))
    codes: list[str] = ["EXTRACTION_CONFIDENCE_ONLY"]
    if review_status == "REJECTED":
        score = 0
        codes.append("REJECTED_MENTION")
    elif review_status == "ACCEPTED":
        # Human review affects evidence completeness only; never validates exploitation.
        score = min(90, score + 10)
        codes.append("MENTION_REVIEWED")
    else:
        score = min(score, 60)
        codes.append("REVIEW_PENDING")
    if days >= 90:
        freshness = "STALE"
        score = min(score, 30)
        codes.append("OLDER_THAN_90_DAYS")
    elif days >= 30:
        freshness = "AGING"
        score = min(score, 50)
        codes.append("OLDER_THAN_30_DAYS")
    else:
        freshness = "CURRENT"
        codes.append("OBSERVED_WITHIN_30_DAYS")
    return MentionQuality(score=score, freshness=freshness, age_days=days,
                          explanation_codes=tuple(codes))
