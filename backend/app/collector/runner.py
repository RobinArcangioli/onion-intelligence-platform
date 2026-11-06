"""Exécution ponctuelle d'une source autorisée, avec second contrôle avant écriture."""
import asyncio
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.collector.extract import extract_html
from app.analyzers.keywords import RuleSpec, analyze_text, MAX_RULES_PER_JOB
from app.collector.transport import CollectError, fetch_onion_root
from app.collector.policy import emergency_active, read_policy
from app.classifiers.rules import classify_document, RULESET_VERSION
from app.cti.ioc_candidates import extraction_enabled, extract_ioc_mentions, IOC_RULESET_VERSION
from app.alerts.engine import emit_observation_alerts
from app.models import (AuditLog, CrawlJob, DiscoveredOnion, OnionSource, SourcePage, SourceObservation,
                        Watchlist, WatchlistRule, KeywordMatch, ClassificationResult, ThreatIndicator, IocCandidate)
from app.security.onion import canonical_onion_page

# Outer deadline: httpx read timeout alone is idle-based, so trickle responses
# can otherwise keep a job RUNNING indefinitely. This is not a retry budget.
MAX_FETCH_SECONDS = 120


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _allowed(source: OnionSource | None) -> bool:
    return bool(source and source.deleted_at is None and source.is_active
                and source.approved_for_collection and source.collection_enabled)


class NotAuthorizedError(Exception):
    """Une source absente, révoquée, désactivée ou incohérente n'est jamais visitée."""


def _audit(session: Session, source_id: uuid.UUID, action: str, job_id: uuid.UUID, *, origin: str = "TOR_HTTP") -> None:
    session.add(AuditLog(
        actor=session.info.get("actor", "tor_collector") if origin == "OPERATOR_CAPTURE" else "tor_collector", action=action, entity_type="onion_source", entity_id=source_id,
        details=json.dumps({"job_id": str(job_id)}),
    ))


async def collect_one(source_id: uuid.UUID, factory: sessionmaker[Session], *,
                      fetcher=fetch_onion_root,
                      existing_job_id: uuid.UUID | None = None,
                      lease_token: uuid.UUID | None = None) -> tuple[uuid.UUID, str]:
    """Aucun changement réseau hors du fetcher Tor ; une seule URL, une requête.

    Tous les échecs réseau sont mémorisés sous un code générique sans URL de
    destination, corps ni traceback dans la base.
    """
    if emergency_active(read_policy()):
        raise NotAuthorizedError("Collecte désactivée par l'arrêt d'urgence")
    with factory() as session:
        source = session.get(OnionSource, source_id)
        if not _allowed(source):
            raise NotAuthorizedError("Source non autorisée à la collecte")
        queued_job = session.get(CrawlJob, existing_job_id) if existing_job_id else None
        url = job_target(session, source, queued_job)
        if url is None:
            raise NotAuthorizedError("Adresse enregistrée invalide ou retirée")
        rules = active_rules(session)
        if existing_job_id is None:
            job = CrawlJob(source_id=source_id, status="RUNNING", started_at=_utcnow())
            session.add(job)
            session.flush()
            job_id = job.id
            _audit(session, source_id, "collection.start", job_id)
            session.commit()
        else:
            # A queued job can only run under the token returned by claim_one.
            # Check in SQL so timezone-aware comparisons work on PostgreSQL
            # and SQLite. The final write repeats the check with a row lock.
            if lease_token is None or session.scalar(select(CrawlJob.id).where(
                CrawlJob.id == existing_job_id, CrawlJob.source_id == source_id,
                CrawlJob.status == "RUNNING", CrawlJob.lease_token == lease_token,
                CrawlJob.lease_expires_at > _utcnow(),
            )) is None:
                raise NotAuthorizedError("Bail de collecte absent ou expiré")
            job_id = existing_job_id

    if emergency_active(read_policy()):
        return job_id, "STOPPED"
    try:
        # Cancellation propagates to httpx. No fallback transport or retry.
        # Enforce a wall-clock limit even when a server trickles bytes forever.
        async with asyncio.timeout(MAX_FETCH_SECONDS):
            result = await fetcher(url)
        extracted = extract_html(result.body, result.encoding, content_type=result.content_type, page_url=url)
        if result.content_type == "text/html" and browser_check(extracted.transient_text):
            raise CollectError("BROWSER_CHECK_REQUIRED")
        analyzed = analyze_page(extracted, rules)
    except TimeoutError:
        error_code = "FETCH_TIMEOUT"
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
        # Lock order matches worker.claim_one: job first, then source.
        job = session.scalar(select(CrawlJob).where(CrawlJob.id == job_id).with_for_update())
        if job is None or job.status != "RUNNING":
            return job_id, job.status if job is not None else "LEASE_LOST"
        if emergency_active(read_policy()):
            return job_id, "STOPPED"
        # Fencing is checked before ANY observation, indicator, discovery,
        # source availability change or audit event can be persisted.
        if existing_job_id is not None and (
            lease_token is None or session.scalar(select(CrawlJob.id).where(
                CrawlJob.id == job_id, CrawlJob.lease_token == lease_token,
                CrawlJob.lease_expires_at > _utcnow(),
            )) is None
        ):
            return job_id, "LEASE_LOST"
        source = session.scalar(select(OnionSource).where(OnionSource.id == source_id).with_for_update())
        if job_target(session, source, job) != url:
            error_code = "AUTHORIZATION_REVOKED"
        if error_code is not None:
            if error_code == "TOR_NETWORK_ERROR" and _allowed(source):
                source.availability_status = "UNAVAILABLE"
            job.status = "FAILED"
            job.error_code = error_code
            job.finished_at = _utcnow()
            job.lease_token = None
            job.lease_expires_at = None
            _audit(session, source_id, "collection.failed", job_id)
            session.commit()
            return job_id, "FAILED"

        store_observation(session, source, job, extracted, analyzed,
                          http_status=result.status, content_type=result.content_type,
                          response_bytes=len(result.body))
        source.availability_status = "AVAILABLE"
        # Final fence: even a slow post-fetch write must remain in lease.
        if existing_job_id is not None and session.scalar(select(CrawlJob.id).where(
            CrawlJob.id == job_id, CrawlJob.lease_token == lease_token,
            CrawlJob.lease_expires_at > _utcnow(),
        )) is None:
            session.rollback()  # Drop all pending observations and side effects.
            return job_id, "LEASE_LOST"
        if emergency_active(read_policy()):
            session.rollback()
            return job_id, "STOPPED"
        job.status = "COMPLETED"
        job.finished_at = _utcnow()
        job.lease_token = None
        job.lease_expires_at = None
        _audit(session, source_id, "collection.completed", job_id)
        session.commit()
        return job_id, "COMPLETED"


def job_target(session: Session, source: OnionSource | None, job: CrawlJob | None = None) -> str | None:
    if not _allowed(source):
        return None
    url = source.canonical_url
    if job is not None and job.page_id is not None:
        page = session.get(SourcePage, job.page_id, populate_existing=True)
        if page is None or not page.is_active or page.source_id != source.id:
            return None
        url = page.url
    elif session.scalar(select(SourcePage.id).where(SourcePage.source_id == source.id,
                                                     SourcePage.url == url,
                                                     SourcePage.is_active.is_(False))):
        return None
    try:
        return url if canonical_onion_page(url) == url else None
    except ValueError:
        return None


def active_rules(session: Session) -> list[RuleSpec]:
    rows = session.scalars(
        select(WatchlistRule).join(Watchlist, Watchlist.id == WatchlistRule.watchlist_id)
        .where(Watchlist.is_active.is_(True), WatchlistRule.is_active.is_(True))
        .order_by(WatchlistRule.created_at, WatchlistRule.id).limit(MAX_RULES_PER_JOB)
    ).all()
    return [RuleSpec(row.id, row.phrase, row.weight) for row in rows]


def analyze_page(extracted, rules):
    analysis = analyze_text(extracted.transient_text, rules)
    classification = classify_document(extracted.transient_text, title=extracted.title, description=extracted.description)
    ioc_mentions = (extract_ioc_mentions(extracted.transient_text)
                    if extraction_enabled() and not classification.quarantine else ())
    return analysis, classification, ioc_mentions


def store_observation(session: Session, source: OnionSource, job: CrawlJob, extracted, analyzed, *,
                      http_status: int, content_type: str, response_bytes: int,
                      origin: str = "TOR_HTTP") -> SourceObservation:
    source_id, job_id = source.id, job.id
    analysis, classification, ioc_mentions = analyzed
    previous_page = SourceObservation.page_id == job.page_id
    legacy_page = job.page_id is None or session.get(SourcePage, job.page_id).url == source.canonical_url
    if legacy_page and job.page_id is not None:
        previous_page = or_(previous_page, SourceObservation.page_id.is_(None))
    prior = session.scalar(select(SourceObservation)
                           .where(SourceObservation.source_id == source_id, previous_page)
                           .order_by(SourceObservation.created_at.desc(), SourceObservation.id.desc())
                           .limit(1))
    if prior is None:
        change_status = "FIRST_SEEN"
    elif prior.text_sha256 == extracted.text_sha256:
        change_status = "UNCHANGED"
    else:
        change_status = "MODIFIED"
    observation = SourceObservation(
        job_id=job_id, source_id=source_id, page_id=job.page_id, origin=origin, http_status=http_status,
        content_type=content_type, response_bytes=response_bytes,
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
    # Opt-in only: no IOC is stored for quarantined content, and no IOC
    # automatically generates an alert or external enrichment request.
    for mention in ioc_mentions:
        session.add(IocCandidate(
            observation_id=observation.id, source_id=source_id,
            indicator_type=mention.indicator_type,
            normalized_value=mention.normalized_value,
            confidence=mention.confidence, evidence_codes=[mention.evidence_code],
            ruleset_version=IOC_RULESET_VERSION,
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
        _audit(session, source_id, "collection.sensitive_quarantine", job_id, origin=origin)
    emit_observation_alerts(session, observation, legacy_scope=legacy_page)
    return observation


def browser_check(text: str) -> bool:
    if len(text) > 1000:
        return False
    text = text.casefold()
    return ("checking your browser" in text or "verify you are human" in text
            or all(word in text for word in ("javascript", "browser", "refresh"))
            or all(word in text for word in ("queue", "wait", "refresh")))
