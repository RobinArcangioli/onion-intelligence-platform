"""Exécution ponctuelle d'une source autorisée, avec second contrôle avant écriture."""
import asyncio
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.collector.extract import extract_html
from app.analyzers.keywords import RuleSpec, analyze_text, MAX_RULES_PER_JOB
from app.collector.transport import CollectError, fetch_onion_root
from app.classifiers.rules import classify_document, RULESET_VERSION
from app.alerts.engine import emit_observation_alerts
from app.models import (AuditLog, CrawlJob, DiscoveredOnion, OnionSource, SourceObservation,
                        Watchlist, WatchlistRule, KeywordMatch, ClassificationResult, ThreatIndicator)
from app.security.onion import canonical_onion_root


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _allowed(source: OnionSource | None) -> bool:
    return bool(source and source.deleted_at is None and source.is_active
                and source.approved_for_collection and source.collection_enabled)


class NotAuthorizedError(Exception):
    """Une source absente, révoquée, désactivée ou incohérente n'est jamais visitée."""


def _audit(session: Session, source_id: uuid.UUID, action: str, job_id: uuid.UUID) -> None:
    session.add(AuditLog(
        actor="tor_collector", action=action, entity_type="onion_source", entity_id=source_id,
        details=json.dumps({"job_id": str(job_id)}),
    ))


async def collect_one(source_id: uuid.UUID, factory: sessionmaker[Session], *,
                      fetcher=fetch_onion_root,
                      existing_job_id: uuid.UUID | None = None) -> tuple[uuid.UUID, str]:
    """Aucun changement réseau hors du fetcher Tor ; une seule racine, une requête.

    Tous les échecs réseau sont mémorisés sous un code générique sans URL de
    destination, corps ni traceback dans la base.
    """
    with factory() as session:
        source = session.get(OnionSource, source_id)
        if not _allowed(source):
            raise NotAuthorizedError("Source non autorisée à la collecte")
        try:
            if canonical_onion_root(source.canonical_url) != source.canonical_url:
                raise ValueError("Non canonique")
        except ValueError as exc:
            raise NotAuthorizedError("Adresse enregistrée invalide") from exc
        url = source.canonical_url
        # Active rules are snapshotted once; later edits apply on future jobs only.
        active_rules = session.scalars(
            select(WatchlistRule).join(Watchlist, Watchlist.id == WatchlistRule.watchlist_id)
            .where(Watchlist.is_active.is_(True), WatchlistRule.is_active.is_(True))
            .order_by(WatchlistRule.created_at, WatchlistRule.id)
            .limit(MAX_RULES_PER_JOB)
        ).all()
        rules = [RuleSpec(item.id, item.phrase, item.weight) for item in active_rules]
        if existing_job_id is None:
            job = CrawlJob(source_id=source_id, status="RUNNING", started_at=_utcnow())
            session.add(job)
            session.flush()
            job_id = job.id
            _audit(session, source_id, "collection.start", job_id)
            session.commit()
        else:
            job = session.get(CrawlJob, existing_job_id)
            if job is None or job.source_id != source_id or job.status != "RUNNING":
                raise NotAuthorizedError("Job non réclamé par le collecteur")
            job_id = existing_job_id

    try:
        result = await fetcher(url)
        extracted = extract_html(result.body, result.encoding, content_type=result.content_type, page_url=url)
        analysis = analyze_text(extracted.transient_text, rules)
        classification = classify_document(extracted.transient_text, title=extracted.title, description=extracted.description)
    except CollectError as exc:
        error_code = exc.code
    except Exception:
        # Ne pas conserver les traces d'un contenu non fiable dans la base.
        error_code = "COLLECTION_FAILED"
    else:
        error_code = None

    with factory() as session:
        # Le verrou évite une décision concurrente pendant la finalisation ; si
        # l'autorisation a été révoquée pendant le fetch, aucun contenu n'est gardé.
        source = session.scalar(select(OnionSource).where(OnionSource.id == source_id).with_for_update())
        job = session.get(CrawlJob, job_id)
        if not _allowed(source):
            error_code = "AUTHORIZATION_REVOKED"
        # A killed/stale worker must never overwrite a job externally closed.
        if job.status != "RUNNING":
            return job_id, job.status
        if error_code is not None:
            if error_code == "TOR_NETWORK_ERROR" and _allowed(source):
                source.availability_status = "UNAVAILABLE"
            job.status = "FAILED"
            job.error_code = error_code
            job.finished_at = _utcnow()
            _audit(session, source_id, "collection.failed", job_id)
            session.commit()
            return job_id, "FAILED"

        prior = session.scalar(select(SourceObservation)
                               .where(SourceObservation.source_id == source_id)
                               .order_by(SourceObservation.created_at.desc(), SourceObservation.id.desc())
                               .limit(1))
        if prior is None:
            change_status = "FIRST_SEEN"
        elif prior.text_sha256 == extracted.text_sha256:
            change_status = "UNCHANGED"
        else:
            change_status = "MODIFIED"
        observation = SourceObservation(
            job_id=job_id, source_id=source_id, http_status=result.status,
            content_type=result.content_type, response_bytes=len(result.body),
            title="" if classification.quarantine else extracted.title,
            description="" if classification.quarantine else extracted.description,
            text_sha256=extracted.text_sha256, text_length=extracted.text_length,
            discovered_links=0 if classification.quarantine else len(extracted.onion_roots),
            change_status=change_status,
            relevance_score=0 if classification.quarantine else analysis.score,
            keyword_hits=0 if classification.quarantine else sum(hit.occurrences for hit in analysis.hits),
        )
        session.add(observation)
        session.flush()
        for hit in (() if classification.quarantine else analysis.hits):
            session.add(KeywordMatch(observation_id=observation.id, rule_id=hit.rule_id,
                                     occurrences=hit.occurrences, contribution=hit.contribution))
        for suggestion in classification.categories:
            session.add(ClassificationResult(
                observation_id=observation.id, source_id=source_id, category=suggestion.category,
                confidence=suggestion.confidence, evidence_codes=list(suggestion.evidence_codes),
                ruleset_version=RULESET_VERSION, review_status=suggestion.review_status,
            ))
        for indicator in classification.indicators:
            session.add(ThreatIndicator(
                observation_id=observation.id, source_id=source_id, indicator_type=indicator.indicator_type,
                public_reference=indicator.public_reference, verification_status=indicator.verification_status,
                confidence=indicator.confidence, evidence_codes=list(indicator.evidence_codes),
                ruleset_version=RULESET_VERSION,
            ))
        for candidate in (() if classification.quarantine else extracted.candidates):
            target = candidate.root
            existing = session.scalar(select(DiscoveredOnion).where(
                DiscoveredOnion.source_id == source_id,
                DiscoveredOnion.target_url == target,
            ))
            if existing:
                existing.last_seen_at = _utcnow()
                existing.evidence_kind = candidate.evidence_kind
                # Never override operator review or trigger a follow-up collection.
            else:
                session.add(DiscoveredOnion(source_id=source_id, target_url=target,
                                            status="PENDING", evidence_kind=candidate.evidence_kind))
        if classification.quarantine:
            source.collection_enabled = False
            _audit(session, source_id, "collection.sensitive_quarantine", job_id)
        emit_observation_alerts(session, observation)
        source.availability_status = "AVAILABLE"
        job.status = "COMPLETED"
        job.finished_at = _utcnow()
        _audit(session, source_id, "collection.completed", job_id)
        session.commit()
        return job_id, "COMPLETED"
