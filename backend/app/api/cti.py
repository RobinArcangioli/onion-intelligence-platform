"""Authenticated, read-only CTI findings and human classification review.

Reviewing a *category* never confirms a compromise or changes source approval.
"""
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.classifiers.rules import taxonomy
from app.db.session import get_session
from app.models import AuditLog, ClassificationResult, ThreatIndicator, KeywordMatch, WatchlistRule, Watchlist, SourceObservation
from app.schemas.cti import ClassificationOut, ClassificationReview, IndicatorOut
from app.security.api_key import require_api_key

router = APIRouter(prefix="/api/v1/cti", tags=["cti"], dependencies=[Depends(require_api_key)])


@router.get("/taxonomy")
def get_taxonomy() -> dict:
    return {"categories": taxonomy(), "note": "Heuristic evidence, not confirmed attribution."}


@router.get("/classifications")
def list_classifications(
    source_id: uuid.UUID | None = None,
    observation_id: uuid.UUID | None = None,
    category: str | None = Query(None, min_length=2, max_length=64),
    review_status: str | None = Query(None, pattern="^(AUTO_SUGGESTED|REVIEW_REQUIRED|ACCEPTED|REJECTED)$"),
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    db: Session = Depends(get_session),
) -> dict:
    filters = []
    if source_id is not None:
        filters.append(ClassificationResult.source_id == source_id)
    if observation_id is not None:
        filters.append(ClassificationResult.observation_id == observation_id)
    if category is not None:
        filters.append(ClassificationResult.category == category)
    if review_status is not None:
        filters.append(ClassificationResult.review_status == review_status)
    total = db.scalar(select(func.count()).select_from(ClassificationResult).where(*filters)) or 0
    rows = db.scalars(select(ClassificationResult).where(*filters)
                      .order_by(ClassificationResult.created_at.desc(), ClassificationResult.id.desc())
                      .offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [ClassificationOut.model_validate(row) for row in rows]}


@router.get("/classifications/{classification_id}", response_model=ClassificationOut)
def get_classification(classification_id: uuid.UUID, db: Session = Depends(get_session)) -> ClassificationResult:
    row = db.get(ClassificationResult, classification_id)
    if row is None:
        raise HTTPException(404, "Classification not found")
    return row


@router.post("/classifications/{classification_id}/review", response_model=ClassificationOut)
def review_classification(classification_id: uuid.UUID, payload: ClassificationReview,
                          db: Session = Depends(get_session)) -> ClassificationResult:
    row = db.scalar(select(ClassificationResult)
                    .where(ClassificationResult.id == classification_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Classification not found")
    if row.review_status in {"ACCEPTED", "REJECTED"}:
        raise HTTPException(409, "Classification already reviewed")
    row.review_status = payload.decision
    row.review_reason = payload.reason
    row.reviewed_at = datetime.now(timezone.utc)
    db.add(AuditLog(actor="api_key_operator", action="classification.review", entity_type="classification",
                    entity_id=row.id, details=json.dumps({"decision": payload.decision, "reason": payload.reason})))
    db.commit()
    db.refresh(row)
    return row


@router.get("/indicators")
def list_indicators(source_id: uuid.UUID | None = None, observation_id: uuid.UUID | None = None,
                    indicator_type: str | None = Query(None, min_length=2, max_length=40),
                    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                    db: Session = Depends(get_session)) -> dict:
    filters = []
    if source_id is not None:
        filters.append(ThreatIndicator.source_id == source_id)
    if observation_id is not None:
        filters.append(ThreatIndicator.observation_id == observation_id)
    if indicator_type is not None:
        filters.append(ThreatIndicator.indicator_type == indicator_type)
    total = db.scalar(select(func.count()).select_from(ThreatIndicator).where(*filters)) or 0
    rows = db.scalars(select(ThreatIndicator).where(*filters)
                      .order_by(ThreatIndicator.created_at.desc(), ThreatIndicator.id.desc())
                      .offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [IndicatorOut.model_validate(row) for row in rows]}


@router.get("/indicators/{indicator_id}", response_model=IndicatorOut)
def get_indicator(indicator_id: uuid.UUID, db: Session = Depends(get_session)) -> ThreatIndicator:
    row = db.get(ThreatIndicator, indicator_id)
    if row is None:
        raise HTTPException(404, "Indicator not found")
    return row


@router.get("/correlations")
def list_correlations(source_id: uuid.UUID | None = None, watchlist_id: uuid.UUID | None = None,
                      limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                      db: Session = Depends(get_session)) -> dict:
    """Bounded same-observation cooccurrence, NOT corroboration of an allegation.

    Watchlist names, rules and phrase values are deliberately not returned.
    """
    statement = (select(ThreatIndicator.id.label("indicator_id"),
                        ThreatIndicator.observation_id.label("observation_id"),
                        ThreatIndicator.source_id.label("source_id"),
                        Watchlist.id.label("watchlist_id"),
                        func.sum(KeywordMatch.occurrences).label("occurrences"),
                        func.max(SourceObservation.relevance_score).label("relevance_score"))
                 .join(KeywordMatch, KeywordMatch.observation_id == ThreatIndicator.observation_id)
                 .join(WatchlistRule, WatchlistRule.id == KeywordMatch.rule_id)
                 .join(Watchlist, Watchlist.id == WatchlistRule.watchlist_id)
                 .join(SourceObservation, SourceObservation.id == ThreatIndicator.observation_id)
                 .group_by(ThreatIndicator.id, ThreatIndicator.observation_id, ThreatIndicator.source_id, Watchlist.id))
    if source_id is not None:
        statement = statement.where(ThreatIndicator.source_id == source_id)
    if watchlist_id is not None:
        statement = statement.where(Watchlist.id == watchlist_id)
    subquery = statement.subquery()
    total = db.scalar(select(func.count()).select_from(subquery)) or 0
    rows = db.execute(select(subquery).order_by(subquery.c.indicator_id, subquery.c.watchlist_id)
                      .limit(limit).offset(offset)).mappings().all()
    return {"total": total, "limit": limit, "offset": offset,
            "disclaimer": "Cooccurrence only; no confirmation of the reported claim.",
            "items": [dict(row) for row in rows]}
