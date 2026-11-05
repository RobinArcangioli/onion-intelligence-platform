"""Authenticated, read-only CTI findings and human classification review.

Reviewing a *category* never confirms a compromise or changes source approval.
"""
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session
from app.classifiers.rules import taxonomy
from app.cti.public_references import canonical_cve
from app.db.session import get_session
from app.models import AuditLog, ClassificationResult, ThreatIndicator, IocCandidate, KeywordMatch, WatchlistRule, Watchlist, SourceObservation
from app.schemas.cti import ClassificationOut, ClassificationReview, IndicatorOut, IndicatorReview, IocCandidateOut, IocCandidateReview
from app.security.api_key import require_api_key, require_role

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


@router.post("/classifications/{classification_id}/review", response_model=ClassificationOut, dependencies=[Depends(require_role("ANALYST"))])
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
    db.add(AuditLog(actor=db.info.get("actor", "api_key_operator"), action="classification.review", entity_type="classification",
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


@router.post("/indicators/{indicator_id}/review", response_model=IndicatorOut,
             dependencies=[Depends(require_role("ANALYST"))])
def review_public_indicator(indicator_id: uuid.UUID, payload: IndicatorReview,
                            db: Session = Depends(get_session)) -> ThreatIndicator:
    """Review the *observation of a public CVE reference*, never its truth or severity."""
    row = db.scalar(select(ThreatIndicator).where(ThreatIndicator.id == indicator_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Indicator not found")
    if row.indicator_type != "PUBLIC_CVE_REFERENCE" or canonical_cve(row.public_reference) is None:
        raise HTTPException(409, "Only public CVE references may be reviewed here")
    if row.review_status != "PENDING":
        raise HTTPException(409, "Indicator already reviewed")
    if payload.decision == "REJECTED" and payload.analyst_priority != "UNASSESSED":
        raise HTTPException(422, "Rejected references cannot receive priority")
    if len(payload.reason.strip()) < 10:
        raise HTTPException(422, "A meaningful review reason is required")
    row.review_status = payload.decision
    row.analyst_priority = payload.analyst_priority
    row.review_reason = payload.reason.strip()
    row.reviewed_at = datetime.now(timezone.utc)
    db.add(AuditLog(actor=db.info.get("actor", "api_key_operator"), action="indicator.review",
                    entity_type="threat_indicator", entity_id=row.id,
                    details=json.dumps({"decision": payload.decision,
                                        "analyst_priority": payload.analyst_priority})))
    db.commit()
    db.refresh(row)
    return row


@router.get("/public-references")
def list_public_references(reference: str | None = Query(None, min_length=13, max_length=17),
                           limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=10000),
                           db: Session = Depends(get_session)) -> dict:
    """Cross-source co-occurrence of *public CVE labels*, not corroboration or attribution.

    Rejected false positives are excluded, but PENDING candidates remain clearly
    distinguishable from reviewed mentions. Grouping never returns page content.
    """
    filters = [ThreatIndicator.indicator_type == "PUBLIC_CVE_REFERENCE",
               ThreatIndicator.review_status != "REJECTED"]
    if reference is not None:
        normalized = canonical_cve(reference)
        if normalized is None:
            raise HTTPException(422, "Invalid public CVE reference")
        filters.append(ThreatIndicator.public_reference == normalized)
    grouped = (select(
        ThreatIndicator.public_reference.label("reference"),
        func.count(ThreatIndicator.id).label("mentions"),
        func.count(func.distinct(ThreatIndicator.source_id)).label("source_count"),
        func.count(func.distinct(ThreatIndicator.observation_id)).label("observation_count"),
        func.sum(case((ThreatIndicator.review_status == "ACCEPTED", 1), else_=0)).label("reviewed_mentions"),
        func.min(ThreatIndicator.created_at).label("first_seen_at"),
        func.max(ThreatIndicator.created_at).label("last_seen_at"),
    ).where(*filters)
     .group_by(ThreatIndicator.public_reference).subquery())
    total = db.scalar(select(func.count()).select_from(grouped)) or 0
    rows = db.execute(select(grouped).order_by(grouped.c.source_count.desc(), grouped.c.reference)
                      .limit(limit).offset(offset)).mappings().all()
    return {"total": total, "limit": limit, "offset": offset,
            "disclaimer": "Public CVE co-occurrence only. Mentions, confidence and analyst priority do not verify exploitation, severity or attribution.",
            "items": [dict(row) for row in rows]}


@router.get("/public-references/{reference}/evidence")
def public_reference_evidence(reference: str,
                              limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=10000),
                              db: Session = Depends(get_session)) -> dict:
    """Bounded provenance for an exact public label (source/observation IDs only)."""
    normalized = canonical_cve(reference)
    if normalized is None:
        raise HTTPException(422, "Invalid public CVE reference")
    filters = [ThreatIndicator.indicator_type == "PUBLIC_CVE_REFERENCE",
               ThreatIndicator.public_reference == normalized,
               ThreatIndicator.review_status != "REJECTED"]
    total = db.scalar(select(func.count()).select_from(ThreatIndicator).where(*filters)) or 0
    rows = db.scalars(select(ThreatIndicator).where(*filters)
                      .order_by(ThreatIndicator.created_at.desc(), ThreatIndicator.id.desc())
                      .limit(limit).offset(offset)).all()
    return {"reference": normalized, "total": total, "limit": limit, "offset": offset,
            "disclaimer": "Provenance of documentary mentions; no confirmation of the underlying claim.",
            "items": [{"indicator_id": x.id, "observation_id": x.observation_id,
                       "source_id": x.source_id, "observed_at": x.created_at,
                       "review_status": x.review_status, "confidence": x.confidence,
                       "analyst_priority": x.analyst_priority,
                       "evidence_codes": x.evidence_codes,
                       "ruleset_version": x.ruleset_version} for x in rows]}


@router.get("/ioc-candidates", dependencies=[Depends(require_role("ANALYST"))])
def list_ioc_candidates(
    source_id: uuid.UUID | None = None,
    observation_id: uuid.UUID | None = None,
    indicator_type: str | None = Query(None, pattern="^(DOMAIN|IPV4|IPV6|SHA256)$"),
    review_status: str | None = Query(None, pattern="^(PENDING|ACCEPTED|REJECTED)$"),
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=10000),
    db: Session = Depends(get_session),
) -> dict:
    """Bounded analyst-only list: explicit mentions, not verified threats."""
    filters = []
    if source_id is not None:
        filters.append(IocCandidate.source_id == source_id)
    if observation_id is not None:
        filters.append(IocCandidate.observation_id == observation_id)
    if indicator_type is not None:
        filters.append(IocCandidate.indicator_type == indicator_type)
    if review_status is not None:
        filters.append(IocCandidate.review_status == review_status)
    total = db.scalar(select(func.count()).select_from(IocCandidate).where(*filters)) or 0
    rows = db.scalars(select(IocCandidate).where(*filters)
                      .order_by(IocCandidate.created_at.desc(), IocCandidate.id.desc())
                      .limit(limit).offset(offset)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "disclaimer": "IOC mentions only. Review does not confirm maliciousness, ownership or compromise.",
            "items": [IocCandidateOut.model_validate(row) for row in rows]}


@router.post("/ioc-candidates/{candidate_id}/review", response_model=IocCandidateOut,
             dependencies=[Depends(require_role("ANALYST"))])
def review_ioc_candidate(candidate_id: uuid.UUID, payload: IocCandidateReview,
                         db: Session = Depends(get_session)) -> IocCandidate:
    candidate = db.scalar(select(IocCandidate).where(IocCandidate.id == candidate_id).with_for_update())
    if candidate is None:
        raise HTTPException(404, "IOC candidate not found")
    if candidate.review_status != "PENDING":
        raise HTTPException(409, "IOC candidate already reviewed")
    if payload.decision == "REJECTED" and (
        payload.analyst_priority != "UNASSESSED" or payload.reason_code == "PUBLIC_REFERENCE_CONFIRMED"
    ):
        raise HTTPException(422, "Rejected candidates must use a rejection reason and no priority")
    if payload.decision == "ACCEPTED" and payload.reason_code != "PUBLIC_REFERENCE_CONFIRMED":
        raise HTTPException(422, "Accepted candidate requires a reference review")
    candidate.review_status = payload.decision
    candidate.analyst_priority = payload.analyst_priority
    candidate.review_reason = payload.reason_code
    candidate.reviewed_at = datetime.now(timezone.utc)
    # Never log normalized_values, page excerpts or analyst-supplied free text.
    db.add(AuditLog(actor=db.info.get("actor", "api_key_operator"), action="ioc_candidate.review",
                    entity_type="ioc_candidate", entity_id=candidate.id,
                    details=json.dumps({"decision": payload.decision, "reason_code": payload.reason_code,
                                        "priority": payload.analyst_priority})))
    db.commit()
    db.refresh(candidate)
    return candidate


@router.get("/ioc-correlations", dependencies=[Depends(require_role("ANALYST"))])
def list_ioc_correlations(
    indicator_type: str | None = Query(None, pattern="^(DOMAIN|IPV4|IPV6|SHA256)$"),
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=10000),
    db: Session = Depends(get_session),
) -> dict:
    """Only analyst-accepted mentions are correlated, with no external lookup."""
    filters = [IocCandidate.review_status == "ACCEPTED"]
    if indicator_type is not None:
        filters.append(IocCandidate.indicator_type == indicator_type)
    grouped = (select(IocCandidate.indicator_type.label("indicator_type"),
                      IocCandidate.normalized_value.label("normalized_value"),
                      func.count(IocCandidate.id).label("mentions"),
                      func.count(func.distinct(IocCandidate.source_id)).label("source_count"),
                      func.count(func.distinct(IocCandidate.observation_id)).label("observation_count"),
                      func.min(IocCandidate.created_at).label("first_seen_at"),
                      func.max(IocCandidate.created_at).label("last_seen_at"))
               .where(*filters)
               .group_by(IocCandidate.indicator_type, IocCandidate.normalized_value).subquery())
    total = db.scalar(select(func.count()).select_from(grouped)) or 0
    rows = db.execute(select(grouped)
                      .order_by(grouped.c.source_count.desc(), grouped.c.indicator_type,
                                grouped.c.normalized_value)
                      .limit(limit).offset(offset)).mappings().all()
    return {"total": total, "limit": limit, "offset": offset,
            "disclaimer": "Cross-source co-occurrence of reviewed mentions; not proof of compromise.",
            "items": [dict(row) for row in rows]}


@router.get("/quality-preview", dependencies=[Depends(require_role("ANALYST"))])
def quality_preview(
    kind: str = Query("IOC", pattern="^(IOC|CVE)$"),
    review_status: str | None = Query(None, pattern="^(PENDING|ACCEPTED|REJECTED)$"),
    limit: int = Query(30, ge=1, le=50), offset: int = Query(0, ge=0, le=10000),
    db: Session = Depends(get_session),
) -> dict:
    """Bounded read-only mention-quality rubric, not an automated threat score."""
    from app.cti.quality import mention_quality, RUBRIC_VERSION
    model = IocCandidate if kind == "IOC" else ThreatIndicator
    filters = []
    if kind == "CVE":
        filters.append(ThreatIndicator.indicator_type == "PUBLIC_CVE_REFERENCE")
    if review_status is not None:
        filters.append(model.review_status == review_status)
    total = db.scalar(select(func.count()).select_from(model).where(*filters)) or 0
    rows = db.scalars(select(model).where(*filters)
                      .order_by(model.created_at.desc(), model.id.desc())
                      .limit(limit).offset(offset)).all()
    now = datetime.now(timezone.utc)
    items = []
    for row in rows:
        q = mention_quality(confidence=row.confidence, review_status=row.review_status,
                            observed_at=row.created_at, as_of=now)
        items.append({
            "id": row.id, "kind": kind, "indicator_type": row.indicator_type,
            "reference": row.normalized_value if kind == "IOC" else row.public_reference,
            "observation_id": row.observation_id, "source_id": row.source_id,
            "original_confidence": row.confidence,
            "review_status": row.review_status, "analyst_priority": row.analyst_priority,
            "observed_at": row.created_at,
            "documentary_quality": q.score, "freshness": q.freshness,
            "age_days": q.age_days, "explanation_codes": q.explanation_codes,
            "rubric_version": q.rubric_version,
        })
    return {"total": total, "limit": limit, "offset": offset,
            "rubric_version": RUBRIC_VERSION,
            "disclaimer": "Documentary mention quality only; not CVSS, maliciousness, attribution or likelihood of compromise. Analyst priority stays separate.",
            "items": items}


@router.get("/cve-ioc-links", dependencies=[Depends(require_role("ANALYST"))])
def cve_ioc_links(
    reference: str | None = Query(None, min_length=13, max_length=17),
    indicator_type: str | None = Query(None, pattern="^(DOMAIN|IPV4|IPV6|SHA256)$"),
    limit: int = Query(30, ge=1, le=50), offset: int = Query(0, ge=0, le=10000),
    db: Session = Depends(get_session),
) -> dict:
    """Only reviewed references in the SAME observation. No semantic relationship inferred."""
    filters = [ThreatIndicator.indicator_type == "PUBLIC_CVE_REFERENCE",
               ThreatIndicator.review_status == "ACCEPTED",
               IocCandidate.review_status == "ACCEPTED",
               ThreatIndicator.source_id == IocCandidate.source_id]
    if reference is not None:
        normalized = canonical_cve(reference)
        if normalized is None:
            raise HTTPException(422, "Invalid CVE label")
        filters.append(ThreatIndicator.public_reference == normalized)
    if indicator_type is not None:
        filters.append(IocCandidate.indicator_type == indicator_type)
    joined = (select(
        ThreatIndicator.public_reference.label("cve"),
        IocCandidate.indicator_type.label("ioc_type"),
        IocCandidate.normalized_value.label("ioc_value"),
        func.count(func.distinct(ThreatIndicator.observation_id)).label("observation_count"),
        func.count(func.distinct(ThreatIndicator.source_id)).label("source_count"),
        func.min(ThreatIndicator.created_at).label("first_seen_at"),
        func.max(ThreatIndicator.created_at).label("last_seen_at"),
    ).join(IocCandidate, IocCandidate.observation_id == ThreatIndicator.observation_id)
     .where(*filters)
     .group_by(ThreatIndicator.public_reference, IocCandidate.indicator_type,
               IocCandidate.normalized_value).subquery())
    total = db.scalar(select(func.count()).select_from(joined)) or 0
    rows = db.execute(select(joined).order_by(joined.c.source_count.desc(),
                                              joined.c.cve, joined.c.ioc_type,
                                              joined.c.ioc_value)
                      .limit(limit).offset(offset)).mappings().all()
    return {"total": total, "limit": limit, "offset": offset,
            "relation": "SAME_OBSERVATION_ONLY",
            "disclaimer": "Reviewed documentary mentions from the same observation only. No causal link, exploitation or compromise inferred.",
            "items": [dict(row) for row in rows]}


@router.get("/review-history/{kind}/{mention_id}", dependencies=[Depends(require_role("ANALYST"))])
def review_history(kind: str, mention_id: uuid.UUID,
                   limit: int = Query(30, ge=1, le=50), offset: int = Query(0, ge=0, le=10000),
                   db: Session = Depends(get_session)) -> dict:
    """Whitelist of existing audit metadata. Never expose review free text or raw evidence."""
    if kind not in {"IOC", "CVE"}:
        raise HTTPException(422, "Unknown mention kind")
    model = IocCandidate if kind == "IOC" else ThreatIndicator
    row = db.get(model, mention_id)
    if row is None or (kind == "CVE" and row.indicator_type != "PUBLIC_CVE_REFERENCE"):
        raise HTTPException(404, "Mention not found")
    entity_type, action = (("ioc_candidate", "ioc_candidate.review") if kind == "IOC"
                           else ("threat_indicator", "indicator.review"))
    filters = [AuditLog.entity_type == entity_type, AuditLog.entity_id == mention_id,
               AuditLog.action == action]
    total = db.scalar(select(func.count()).select_from(AuditLog).where(*filters)) or 0
    rows = db.scalars(select(AuditLog).where(*filters)
                      .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                      .limit(limit).offset(offset)).all()
    out = []
    for event in rows:
        try:
            metadata = json.loads(event.details)
            metadata = metadata if isinstance(metadata, dict) else {}
        except (ValueError, TypeError):
            metadata = {}
        # Allowlisted fields only. Never return free-text reviews or captured values.
        out.append({"audit_id": event.id, "actor": event.actor,
                    "at": event.created_at,
                    "decision": metadata.get("decision") if metadata.get("decision") in {"ACCEPTED", "REJECTED"} else "UNKNOWN",
                    "analyst_priority": (metadata.get("priority") or metadata.get("analyst_priority"))
                    if (metadata.get("priority") or metadata.get("analyst_priority")) in {"UNASSESSED", "LOW", "MEDIUM", "HIGH"} else "UNASSESSED",
                    "reason_code": metadata.get("reason_code") if metadata.get("reason_code") in {
                        "PUBLIC_REFERENCE_CONFIRMED", "NON_INDICATOR", "MISPARSED", "OUT_OF_SCOPE"} else None})
    return {"kind": kind, "mention_id": mention_id, "total": total,
            "limit": limit, "offset": offset, "items": out}
