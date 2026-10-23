"""Watchlists, explainable hits, human discovery decisions. Network-free API."""
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analyzers.keywords import MAX_RULES_PER_JOB, normalized_phrase
from app.db.session import get_session
from app.models import (AuditLog, DiscoveredOnion, KeywordMatch, SourceObservation,
                        Watchlist, WatchlistRule)
from app.schemas.collection import DiscoveryOut
from app.schemas.intelligence import (ActiveUpdate, DiscoveryReview, RuleCreate,
                                      RuleOut, WatchlistCreate, WatchlistOut)
from app.security.api_key import require_api_key, require_role

router = APIRouter(prefix="/api/v1", tags=["intelligence"], dependencies=[Depends(require_api_key)])


def _audit(db: Session, action: str, kind: str, item_id: uuid.UUID, reason: str = "Manual check") -> None:
    db.add(AuditLog(actor=db.info.get("actor", "api_key_operator"), action=action, entity_type=kind,
                    entity_id=item_id, details=json.dumps({"reason": reason})))


def _watchlist(db: Session, item_id: uuid.UUID) -> Watchlist:
    row = db.get(Watchlist, item_id)
    if row is None:
        raise HTTPException(404, "Watchlist not found")
    return row


def _rule(db: Session, item_id: uuid.UUID) -> WatchlistRule:
    row = db.get(WatchlistRule, item_id)
    if row is None:
        raise HTTPException(404, "Rule not found")
    return row


@router.get("/watchlists")
def list_watchlists(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                    db: Session = Depends(get_session)) -> dict:
    total = db.scalar(select(func.count()).select_from(Watchlist)) or 0
    rows = db.scalars(select(Watchlist).order_by(Watchlist.created_at, Watchlist.id)
                      .offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [WatchlistOut.model_validate(x) for x in rows]}


@router.post("/watchlists", response_model=WatchlistOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_role("ANALYST"))])
def create_watchlist(payload: WatchlistCreate, db: Session = Depends(get_session)) -> Watchlist:
    row = Watchlist(name=payload.name)
    try:
        db.add(row)
        db.flush()
        _audit(db, "watchlist.create", "watchlist", row.id)
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Watchlist already exists") from exc


@router.patch("/watchlists/{watchlist_id}", response_model=WatchlistOut, dependencies=[Depends(require_role("ANALYST"))])
def update_watchlist(watchlist_id: uuid.UUID, payload: ActiveUpdate,
                     db: Session = Depends(get_session)) -> Watchlist:
    row = _watchlist(db, watchlist_id)
    row.is_active = payload.is_active
    _audit(db, "watchlist.active", "watchlist", row.id, payload.reason)
    db.commit()
    db.refresh(row)
    return row


@router.get("/watchlists/{watchlist_id}/rules")
def list_rules(watchlist_id: uuid.UUID, limit: int = Query(50, ge=1, le=100),
               offset: int = Query(0, ge=0), db: Session = Depends(get_session)) -> dict:
    _watchlist(db, watchlist_id)
    condition = WatchlistRule.watchlist_id == watchlist_id
    total = db.scalar(select(func.count()).select_from(WatchlistRule).where(condition)) or 0
    rows = db.scalars(select(WatchlistRule).where(condition)
                      .order_by(WatchlistRule.created_at, WatchlistRule.id).offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [RuleOut.model_validate(x) for x in rows]}


@router.post("/watchlists/{watchlist_id}/rules", response_model=RuleOut, status_code=201, dependencies=[Depends(require_role("ANALYST"))])
def create_rule(watchlist_id: uuid.UUID, payload: RuleCreate,
                db: Session = Depends(get_session)) -> WatchlistRule:
    _watchlist(db, watchlist_id)
    # Ensure all enabled rules fit into the deterministic scan limit.
    count = db.scalar(select(func.count()).select_from(WatchlistRule)) or 0
    if count >= MAX_RULES_PER_JOB:
        raise HTTPException(409, "Rule capacity reached")
    row = WatchlistRule(watchlist_id=watchlist_id, phrase=payload.phrase,
                        phrase_normalized=normalized_phrase(payload.phrase), weight=payload.weight)
    try:
        db.add(row)
        db.flush()
        _audit(db, "watchlist.rule.create", "watchlist_rule", row.id)
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Duplicate phrase") from exc


@router.patch("/watchlist-rules/{rule_id}", response_model=RuleOut, dependencies=[Depends(require_role("ANALYST"))])
def update_rule(rule_id: uuid.UUID, payload: ActiveUpdate, db: Session = Depends(get_session)) -> WatchlistRule:
    row = _rule(db, rule_id)
    row.is_active = payload.is_active
    _audit(db, "watchlist.rule.active", "watchlist_rule", row.id, payload.reason)
    db.commit()
    db.refresh(row)
    return row


@router.get("/collection/observations/{observation_id}/analysis")
def observation_analysis(observation_id: uuid.UUID, db: Session = Depends(get_session)) -> dict:
    observation = db.get(SourceObservation, observation_id)
    if not observation:
        raise HTTPException(404, "Observation not found")
    matches = db.execute(select(KeywordMatch, WatchlistRule)
                         .join(WatchlistRule, WatchlistRule.id == KeywordMatch.rule_id)
                         .where(KeywordMatch.observation_id == observation_id)
                         .order_by(KeywordMatch.created_at, KeywordMatch.id)).all()
    return {"observation_id": observation_id, "relevance_score": observation.relevance_score,
            "keyword_hits": observation.keyword_hits, "scoring": "min(100,sum(min(count,3)*weight))",
            "matches": [{"rule_id": rule.id, "phrase": rule.phrase,
                         "occurrences": match.occurrences, "contribution": match.contribution}
                        for match, rule in matches],
            "warning": "Relevance is not evidence of harm or verification."}


@router.post("/collection/discoveries/{discovery_id}/review", response_model=DiscoveryOut, dependencies=[Depends(require_role("ANALYST"))])
def review_discovery(discovery_id: uuid.UUID, payload: DiscoveryReview,
                     db: Session = Depends(get_session)) -> DiscoveredOnion:
    row = db.scalar(select(DiscoveredOnion).where(DiscoveredOnion.id == discovery_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Candidate not found")
    if row.status != "PENDING":
        raise HTTPException(409, "Candidate already reviewed")
    row.status = payload.decision
    row.review_reason = payload.reason
    row.reviewed_at = datetime.now(timezone.utc)
    _audit(db, "discovery.review", "discovered_onion", row.id, payload.reason)
    db.commit()
    db.refresh(row)
    # APPROVED is a review decision only. It NEVER creates an authorized source.
    return row
