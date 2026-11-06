"""Gestion contrôlée des sources : métadonnées, autorisations et audit.

Aucun endpoint ne déclenche de requête Tor, ni n'active collection_enabled.
"""
from dataclasses import replace
import csv
import io
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.core.config import Settings, get_settings
from app.collector.policy import admission_lock, pending_full, read_policy, source_restriction, emergency_active
from app.collector.extract import extract_html
from app.collector.runner import active_rules, analyze_page, store_observation
from app.models import AuditLog, OnionSource, CrawlJob, SourceObservation, SourcePage, SourceSchedule
from app.schemas.collection import JobOut, ObservationOut
from app.security.onion import canonical_onion_page
from app.schemas.source import (
    SourceApproval, SourceAuditOut, SourceCreate, SourceHistory,
    SourceList, SourceOut, SourcePatch, SourceReason,
    SourceImportRequest, SourceImportResult, SourcePageAdd, SourcePageCapture, SourcePageOut,
)
from app.security.api_key import require_api_key, require_role

router = APIRouter(
    prefix="/api/v1/sources", tags=["sources"],
    dependencies=[Depends(require_api_key)],
)


def _source(
    db: Session, source_id: uuid.UUID, *, include_deleted: bool = False, lock: bool = False
) -> OnionSource:
    stmt = select(OnionSource).where(OnionSource.id == source_id)
    if lock:
        stmt = stmt.with_for_update()
    if not include_deleted:
        stmt = stmt.where(OnionSource.deleted_at.is_(None))
    source = db.scalar(stmt)
    if source is None:
        raise HTTPException(status_code=404, detail="Source introuvable")
    return source


def _audit(db: Session, source: OnionSource, action: str, *, reason: str, **extra: object) -> None:
    data = {"reason": reason, **extra}
    db.add(AuditLog(
        actor=db.info.get("actor", "api_key_operator"), action=action,
        entity_type="onion_source", entity_id=source.id,
        details=json.dumps(data, ensure_ascii=False, sort_keys=True),
    ))


def _pause_schedule(db: Session, source: OnionSource, reason: str) -> None:
    """Source revocation/disable also revokes schedule opt-in."""
    schedule = db.get(SourceSchedule, source.id)
    if schedule is not None and schedule.enabled:
        schedule.enabled = False
        _audit(db, source, "schedule.pause_by_source", reason=reason)


def _save(db: Session, source: OnionSource) -> OnionSource:
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("", response_model=SourceList)
def list_sources(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, min_length=1, max_length=160),
    category: str | None = Query(default=None, max_length=60),
    approved: bool | None = Query(default=None),
    active: bool | None = Query(default=None),
    priority: int | None = Query(default=None, ge=1, le=5),
    db: Session = Depends(get_session),
) -> SourceList:
    conditions = [OnionSource.deleted_at.is_(None)]
    if q is not None:
        search = q.strip()
        if not search:
            raise HTTPException(status_code=422, detail="Recherche vide")
        # Échapper % et _ pour une recherche littérale, sans wildcard utilisateur.
        search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{search}%"
        conditions.append(or_(
            OnionSource.name.ilike(pattern, escape="\\"),
            OnionSource.canonical_url.ilike(pattern, escape="\\"),
            OnionSource.description.ilike(pattern, escape="\\"),
            select(SourcePage.id).where(SourcePage.source_id == OnionSource.id,
                SourcePage.is_active.is_(True), SourcePage.url.ilike(pattern, escape="\\")).exists(),
        ))
    if category is not None:
        conditions.append(OnionSource.category == category)
    if approved is not None:
        conditions.append(OnionSource.approved_for_collection == approved)
    if active is not None:
        conditions.append(OnionSource.is_active == active)
    if priority is not None:
        conditions.append(OnionSource.priority == priority)

    total = db.scalar(select(func.count()).select_from(OnionSource).where(*conditions)) or 0
    rows = db.scalars(
        select(OnionSource).where(*conditions)
        .order_by(OnionSource.created_at.desc(), OnionSource.id.desc())
        .offset(offset).limit(limit)
    ).all()
    return SourceList(total=total, limit=limit, offset=offset, items=[SourceOut.model_validate(x) for x in rows])


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_role("ADMIN"))])
def create_source(payload: SourceCreate, db: Session = Depends(get_session)) -> OnionSource:
    source = OnionSource(
        canonical_url=payload.url, name=payload.name,
        description=payload.description, priority=payload.priority,
        authorization_note=payload.authorization_note,
        approved_for_collection=True,
        is_active=True,
        collection_enabled=False,
    )
    try:
        db.add(source)
        db.flush()
        db.add(SourcePage(source_id=source.id, url=source.canonical_url))
        _audit(db, source, "source.create", reason="Manual approval")
        return _save(db, source)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="URL déjà enregistrée (restaurer la source supprimée si nécessaire)",
        ) from exc


def _csv_safe(value: object) -> str:
    """Neutraliser les formules à l'ouverture dans un tableur (CSV injection)."""
    rendered = str(value)
    if rendered.lstrip().startswith(("=", "+", "-", "@")) or rendered.startswith(("\t", "\r", "\n")):
        return "'" + rendered
    return rendered


@router.get("/export.csv", response_class=Response)
def export_sources_csv(db: Session = Depends(get_session)) -> Response:
    """Export CSV borné, sans secret, note d'autorisation ni source supprimée."""
    rows = db.scalars(
        select(OnionSource).where(OnionSource.deleted_at.is_(None))
        .order_by(OnionSource.created_at, OnionSource.id).limit(500)
    ).all()
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["id", "canonical_url", "name", "description", "category", "priority", "is_active", "approved_for_collection"])
    for row in rows:
        writer.writerow([
            str(row.id), _csv_safe(row.canonical_url), _csv_safe(row.name),
            _csv_safe(row.description), _csv_safe(row.category), row.priority,
            row.is_active, row.approved_for_collection,
        ])
    return Response(
        "\ufeff" + stream.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="oip-sources.csv"'},
    )


@router.post("/import", response_model=SourceImportResult, status_code=201, dependencies=[Depends(require_role("ADMIN"))])
def import_sources(payload: SourceImportRequest, db: Session = Depends(get_session)) -> SourceImportResult:
    """Import JSON atomique : 1 à 100 sources validées, aucune visite réseau."""
    urls = [item.url for item in payload.items]
    if len(set(urls)) != len(urls):
        raise HTTPException(status_code=409, detail="Adresses dupliquées dans le lot importé")
    created = []
    try:
        for item in payload.items:
            source = OnionSource(
                canonical_url=item.url, name=item.name,
                description=item.description, priority=item.priority,
                authorization_note=item.authorization_note,
                approved_for_collection=True, is_active=True, collection_enabled=False,
            )
            db.add(source)
            db.flush()
            db.add(SourcePage(source_id=source.id, url=source.canonical_url))
            _audit(db, source, "source.import", reason="Manual import")
            created.append(source)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Une source du lot existe déjà, import annulé") from exc
    for source in created:
        db.refresh(source)
    return SourceImportResult(total=len(created), items=[SourceOut.model_validate(item) for item in created])


@router.get("/{source_id}", response_model=SourceOut)
def get_source(source_id: uuid.UUID, db: Session = Depends(get_session)) -> OnionSource:
    return _source(db, source_id)


@router.patch("/{source_id}", response_model=SourceOut, dependencies=[Depends(require_role("ADMIN"))])
def patch_source(source_id: uuid.UUID, payload: SourcePatch, db: Session = Depends(get_session)) -> OnionSource:
    source = _source(db, source_id, lock=True)
    changed = []
    for name in ("name", "description", "category", "priority"):
        value = getattr(payload, name)
        if value is not None and value != getattr(source, name):
            setattr(source, name, value)
            changed.append(name)
    if changed:
        _audit(db, source, "source.update", reason=payload.reason, fields=sorted(changed))
        return _save(db, source)
    return source


@router.post("/{source_id}/deactivate", response_model=SourceOut, dependencies=[Depends(require_role("ADMIN"))])
def deactivate_source(source_id: uuid.UUID, payload: SourceReason, db: Session = Depends(get_session)) -> OnionSource:
    source = _source(db, source_id, lock=True)
    if source.is_active:
        source.is_active = False
        source.collection_enabled = False
        _pause_schedule(db, source, "source.deactivate")
        _audit(db, source, "source.deactivate", reason=payload.reason)
        return _save(db, source)
    return source


@router.post("/{source_id}/activate", response_model=SourceOut, dependencies=[Depends(require_role("ADMIN"))])
def activate_source(source_id: uuid.UUID, payload: SourceReason, db: Session = Depends(get_session)) -> OnionSource:
    source = _source(db, source_id, lock=True)
    if not source.is_active:
        source.is_active = True
        source.collection_enabled = False
        _audit(db, source, "source.activate", reason=payload.reason)
        return _save(db, source)
    return source


@router.post("/{source_id}/revoke", response_model=SourceOut, dependencies=[Depends(require_role("ADMIN"))])
def revoke_source(source_id: uuid.UUID, payload: SourceReason, db: Session = Depends(get_session)) -> OnionSource:
    source = _source(db, source_id, lock=True)
    if source.approved_for_collection:
        source.approved_for_collection = False
        source.collection_enabled = False
        _pause_schedule(db, source, "source.revoke")
        _audit(db, source, "source.revoke", reason=payload.reason)
        return _save(db, source)
    return source


@router.post("/{source_id}/approve", response_model=SourceOut, dependencies=[Depends(require_role("ADMIN"))])
def approve_source(source_id: uuid.UUID, payload: SourceApproval, db: Session = Depends(get_session)) -> OnionSource:
    source = _source(db, source_id, lock=True)
    source.approved_for_collection = True
    source.collection_enabled = False
    source.authorization_note = payload.authorization_note
    _pause_schedule(db, source, "source.approve")
    _audit(db, source, "source.approve", reason="Manual approval")
    return _save(db, source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role("ADMIN"))])
def delete_source(source_id: uuid.UUID, payload: SourceReason, db: Session = Depends(get_session)) -> Response:
    source = _source(db, source_id, lock=True)
    source.deleted_at = datetime.now(timezone.utc)
    source.is_active = False
    source.approved_for_collection = False
    source.collection_enabled = False
    _pause_schedule(db, source, "source.delete")
    _audit(db, source, "source.delete", reason=payload.reason)
    _save(db, source)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{source_id}/restore", response_model=SourceOut, dependencies=[Depends(require_role("ADMIN"))])
def restore_source(source_id: uuid.UUID, payload: SourceReason, db: Session = Depends(get_session)) -> OnionSource:
    source = _source(db, source_id, include_deleted=True, lock=True)
    if source.deleted_at is None:
        raise HTTPException(status_code=409, detail="Source non supprimée")
    source.deleted_at = None
    source.is_active = False
    source.approved_for_collection = False
    source.collection_enabled = False
    _pause_schedule(db, source, "source.restore")
    _audit(db, source, "source.restore", reason=payload.reason)
    return _save(db, source)


@router.post("/{source_id}/collection/run", status_code=status.HTTP_202_ACCEPTED,
             response_model=JobOut, dependencies=[Depends(require_role("ANALYST"))])
def enqueue_manual_collection(
    source_id: uuid.UUID, payload: SourceReason, db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CrawlJob:
    """Audited one-shot request. NO Tor call, Docker invocation or auto-discovery.

    PostgreSQL source lock serializes requests against approval/revocation, and
    the partial unique index rejects any duplicate active job (also across pods).
    """
    if not settings.manual_collection_enabled:
        raise HTTPException(status_code=503, detail="Collecte manuelle désactivée sur cette instance")
    try:
        policy = read_policy()
        halted = emergency_active(policy)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Politique de collecte invalide") from exc
    if halted:
        raise HTTPException(status_code=503, detail="Arrêt d'urgence de la collecte activé")
    # Global counters need serialization across independent API instances.
    # Acquire this BEFORE the source lock (same ordering as queue_worker).
    admission_lock(db)
    source = _source(db, source_id, lock=True)
    if not (source.is_active and source.approved_for_collection and source.collection_enabled):
        raise HTTPException(status_code=409, detail="Collecte non autorisée pour cette source")
    existing = db.scalar(select(CrawlJob.id).where(
        CrawlJob.source_id == source_id, CrawlJob.status.in_(("PENDING", "RUNNING", "WAITING")),
    ).limit(1))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Une collecte est déjà en attente ou en cours")
    pages = db.scalars(select(SourcePage).where(SourcePage.source_id == source_id)
                       .order_by(SourcePage.url)).all()
    targets = [(page.id, page.url) for page in pages if page.is_active]
    if not pages:
        targets = [(None, source.canonical_url)]
    if not targets:
        raise HTTPException(409, "Ce groupe ne contient aucune URL active")
    try:
        if any(canonical_onion_page(url) != url for _, url in targets):
            raise ValueError("Non canonique")
    except ValueError as exc:
        raise HTTPException(409, "Adresse Onion invalide") from exc
    restriction = source_restriction(db, source_id, policy)
    if restriction:
        raise HTTPException(status_code=429, detail=restriction)
    if pending_full(db, policy):
        raise HTTPException(status_code=429, detail="GLOBAL_QUEUE_FULL")
    jobs = [CrawlJob(source_id=source_id, page_id=page_id, status="PENDING" if index == 0 else "WAITING")
            for index, (page_id, _) in enumerate(targets)]
    db.add_all(jobs)
    first = jobs[0]
    try:
        db.flush()
        _audit(db, source, "collection.enqueue", reason=payload.reason, job_id=str(first.id), urls=len(jobs))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Une collecte est déjà en attente ou en cours") from exc
    db.refresh(first)
    return first


@router.get("/{source_id}/history", response_model=SourceHistory)
def get_source_history(
    source_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_session),
) -> SourceHistory:
    _source(db, source_id, include_deleted=True)
    constraints = (AuditLog.entity_type == "onion_source", AuditLog.entity_id == source_id)
    total = db.scalar(select(func.count()).select_from(AuditLog).where(*constraints)) or 0
    rows = db.scalars(
        select(AuditLog).where(*constraints).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset).limit(limit)
    ).all()
    return SourceHistory(
        total=total, limit=limit, offset=offset,
        items=[SourceAuditOut(
            id=row.id, action=row.action, actor=row.actor,
            details=json.loads(row.details), created_at=row.created_at,
        ) for row in rows],
    )


@router.post("/{source_id}/collection/enable", response_model=SourceOut, dependencies=[Depends(require_role("ADMIN"))])
def enable_collection(source_id: uuid.UUID, payload: SourceReason, db: Session = Depends(get_session)) -> OnionSource:
    """Activation explicite, distincte de l'approbation ; aucun lancement réseau."""
    source = _source(db, source_id, lock=True)
    if not source.is_active or not source.approved_for_collection:
        raise HTTPException(status_code=409, detail="Source inactive ou non autorisée")
    if not source.collection_enabled:
        source.collection_enabled = True
        _audit(db, source, "collection.enable", reason=payload.reason)
        return _save(db, source)
    return source


@router.post("/{source_id}/collection/disable", response_model=SourceOut, dependencies=[Depends(require_role("ADMIN"))])
def disable_collection(source_id: uuid.UUID, payload: SourceReason, db: Session = Depends(get_session)) -> OnionSource:
    source = _source(db, source_id, lock=True)
    if source.collection_enabled:
        source.collection_enabled = False
        _pause_schedule(db, source, "collection.disable")
        _audit(db, source, "collection.disable", reason=payload.reason)
        return _save(db, source)
    return source


def _register_page(db: Session, source: OnionSource, url: str) -> SourcePage:
    # Older registry writers may still create a source without a page row.
    if not db.scalar(select(SourcePage.id).where(SourcePage.source_id == source.id).limit(1)):
        db.add(SourcePage(source_id=source.id, url=source.canonical_url))
        db.flush()
    page = db.scalar(select(SourcePage).where(SourcePage.source_id == source.id, SourcePage.url == url))
    if page is None:
        page = SourcePage(source_id=source.id, url=url)
        db.add(page)
        db.flush()
        _audit(db, source, "source.page.add", reason="Manual selection", page_id=str(page.id))
    elif not page.is_active:
        page.is_active = True
        _audit(db, source, "source.page.restore", reason="Manual selection", page_id=str(page.id))
    return page


@router.get("/{source_id}/pages")
def list_source_pages(source_id: uuid.UUID, limit: int = Query(50, ge=1, le=100),
                      offset: int = Query(0, ge=0), db: Session = Depends(get_session)) -> dict:
    _source(db, source_id)
    scope = (SourcePage.source_id == source_id, SourcePage.is_active.is_(True))
    total = db.scalar(select(func.count()).select_from(SourcePage).where(*scope))
    latest = (select(CrawlJob.id).where(CrawlJob.page_id == SourcePage.id).correlate(SourcePage)
              .order_by(CrawlJob.created_at.desc(), CrawlJob.id.desc()).limit(1).scalar_subquery())
    rows = db.execute(select(SourcePage, CrawlJob.status, CrawlJob.error_code)
                      .outerjoin(CrawlJob, CrawlJob.id == latest).where(*scope)
                      .order_by(SourcePage.url).offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [SourcePageOut(id=page.id, url=page.url, status=state, error_code=error)
                      for page, state, error in rows]}


@router.post("/{source_id}/pages", response_model=SourcePageOut,
             dependencies=[Depends(require_role("ADMIN"))])
def add_source_page(source_id: uuid.UUID, payload: SourcePageAdd,
                    db: Session = Depends(get_session)) -> SourcePage:
    source = _source(db, source_id, lock=True)
    page = _register_page(db, source, payload.url)
    db.commit()
    return page


@router.delete("/{source_id}/pages/{page_id}", status_code=204,
               dependencies=[Depends(require_role("ADMIN"))])
def archive_source_page(source_id: uuid.UUID, page_id: uuid.UUID,
                        db: Session = Depends(get_session)) -> Response:
    source = _source(db, source_id, lock=True)
    page = db.get(SourcePage, page_id)
    if page is None or page.source_id != source.id:
        raise HTTPException(404, "URL introuvable dans ce groupe")
    if page.is_active:
        page.is_active = False
        _audit(db, source, "source.page.archive", reason="Manual removal", page_id=str(page.id))
        db.commit()
    return Response(status_code=204)


@router.post("/{source_id}/pages/capture", response_model=ObservationOut,
             dependencies=[Depends(require_role("ADMIN"))])
def capture_source_page(source_id: uuid.UUID, payload: SourcePageCapture,
                        db: Session = Depends(get_session),
                        settings: Settings = Depends(get_settings)) -> SourceObservation:
    if not settings.manual_collection_enabled or emergency_active(read_policy()):
        raise HTTPException(503, "Analyse désactivée")
    source = _source(db, source_id, lock=True)
    if not (source.is_active and source.approved_for_collection):
        raise HTTPException(409, "Source non autorisée à l’analyse")
    body = payload.text.encode("utf-8")
    extracted = extract_html(body, "utf-8", content_type="text/plain", page_url=payload.url)
    extracted = replace(extracted, candidates=(), onion_roots=())
    if not extracted.text_length:
        raise HTTPException(422, "Texte visible requis")
    existing = db.get(CrawlJob, payload.request_id)
    if existing is not None:
        observation = db.scalar(select(SourceObservation).where(SourceObservation.job_id == existing.id))
        page = db.get(SourcePage, existing.page_id) if existing.page_id else None
        if (existing.source_id == source.id and page and page.url == payload.url and observation
                and observation.origin == "OPERATOR_CAPTURE" and observation.text_sha256 == extracted.text_sha256):
            return observation
        raise HTTPException(409, "Identifiant de capture déjà utilisé")
    page = _register_page(db, source, payload.url)
    now = datetime.now(timezone.utc)
    job = CrawlJob(id=payload.request_id, source_id=source.id, page_id=page.id,
                   status="COMPLETED", started_at=now, finished_at=now)
    db.add(job)
    try:
        db.flush()
        observation = store_observation(db, source, job, extracted, analyze_page(extracted, active_rules(db)),
                                        http_status=0, content_type="text/plain", response_bytes=0,
                                        origin="OPERATOR_CAPTURE")
        _audit(db, source, "collection.capture", reason="Operator visible text",
               page_id=str(page.id), job_id=str(job.id))
        if emergency_active(read_policy()):
            raise HTTPException(503, "Analyse désactivée")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Identifiant de capture déjà utilisé") from exc
    return observation
