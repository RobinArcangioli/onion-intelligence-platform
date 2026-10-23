"""Lecture des jobs et observations ; aucune route HTTP ne lance le collecteur."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.models import CrawlJob, DiscoveredOnion, SourceObservation
from app.schemas.collection import DiscoveryOut, JobOut, ObservationOut
from app.security.api_key import require_api_key

router = APIRouter(prefix="/api/v1/collection", tags=["collection"], dependencies=[Depends(require_api_key)])


def _listing(db: Session, model: type, response_type: type, source_id: uuid.UUID | None, limit: int, offset: int) -> dict:
    conditions = [] if source_id is None else [model.source_id == source_id]
    total = db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0
    rows = db.scalars(select(model).where(*conditions).order_by(model.created_at.desc(), model.id.desc()).offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset, "items": [response_type.model_validate(r) for r in rows]}


@router.get("/jobs")
def list_jobs(source_id: uuid.UUID | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_session)) -> dict:
    return _listing(db, CrawlJob, JobOut, source_id, limit, offset)


@router.get("/latest", response_model=list[JobOut])
def latest_jobs(
    source_ids: list[uuid.UUID] = Query(default=[], max_length=50),
    db: Session = Depends(get_session),
) -> list[CrawlJob]:
    """Latest job per requested source, bounded to the visible UI page."""
    if not source_ids:
        return []
    ranks = (select(
        CrawlJob.id.label("id"),
        func.row_number().over(
            partition_by=CrawlJob.source_id,
            order_by=(CrawlJob.created_at.desc(), CrawlJob.id.desc()),
        ).label("rn"),
    ).where(CrawlJob.source_id.in_(source_ids)).subquery())
    return list(db.scalars(select(CrawlJob).join(ranks, CrawlJob.id == ranks.c.id)
                           .where(ranks.c.rn == 1)).all())


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_session)) -> CrawlJob:
    job = db.get(CrawlJob, job_id)
    if not job:
        raise HTTPException(404, "Job introuvable")
    return job


@router.get("/observations")
def list_observations(source_id: uuid.UUID | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_session)) -> dict:
    return _listing(db, SourceObservation, ObservationOut, source_id, limit, offset)


@router.get("/discoveries")
def list_discoveries(source_id: uuid.UUID | None = None, status: str | None = Query(None, pattern="^(PENDING|APPROVED|REJECTED)$"), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_session)) -> dict:
    conditions = [] if source_id is None else [DiscoveredOnion.source_id == source_id]
    if status is not None:
        conditions.append(DiscoveredOnion.status == status)
    total = db.scalar(select(func.count()).select_from(DiscoveredOnion).where(*conditions)) or 0
    rows = db.scalars(select(DiscoveredOnion).where(*conditions).order_by(DiscoveredOnion.first_seen_at.desc(), DiscoveredOnion.id.desc()).offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset, "items": [DiscoveryOut.model_validate(r) for r in rows]}
