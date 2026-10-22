"""Exécution ponctuelle d'une source autorisée, avec second contrôle avant écriture."""
import asyncio
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.collector.extract import extract_html
from app.collector.transport import CollectError, fetch_onion_root
from app.models import AuditLog, CrawlJob, DiscoveredOnion, OnionSource, SourceObservation
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


async def collect_one(source_id: uuid.UUID, factory: sessionmaker[Session], *, fetcher=fetch_onion_root) -> tuple[uuid.UUID, str]:
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
        job = CrawlJob(source_id=source_id, status="RUNNING", started_at=_utcnow())
        session.add(job)
        session.flush()
        job_id = job.id
        _audit(session, source_id, "collection.start", job_id)
        session.commit()

    try:
        result = await fetcher(url)
        extracted = extract_html(result.body, result.encoding, content_type=result.content_type, page_url=url)
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
        if error_code is not None:
            if error_code == "TOR_NETWORK_ERROR" and _allowed(source):
                source.availability_status = "UNAVAILABLE"
            job.status = "FAILED"
            job.error_code = error_code
            job.finished_at = _utcnow()
            _audit(session, source_id, "collection.failed", job_id)
            session.commit()
            return job_id, "FAILED"

        session.add(SourceObservation(
            job_id=job_id, source_id=source_id, http_status=result.status,
            content_type=result.content_type, response_bytes=len(result.body),
            title=extracted.title, description=extracted.description,
            text_sha256=extracted.text_sha256, text_length=extracted.text_length,
            discovered_links=len(extracted.onion_roots),
        ))
        for target in extracted.onion_roots:
            existing = session.scalar(select(DiscoveredOnion).where(
                DiscoveredOnion.source_id == source_id,
                DiscoveredOnion.target_url == target,
            ))
            if existing:
                existing.last_seen_at = _utcnow()
            else:
                session.add(DiscoveredOnion(source_id=source_id, target_url=target, status="PENDING"))
        source.availability_status = "AVAILABLE"
        job.status = "COMPLETED"
        job.finished_at = _utcnow()
        _audit(session, source_id, "collection.completed", job_id)
        session.commit()
        return job_id, "COMPLETED"
