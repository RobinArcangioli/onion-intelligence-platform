"""Anonymous, read-only public API. No internal IDs, raw source content or error details."""
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import ClassificationResult, CrawlJob, OnionSource, ReportPublication, SourceObservation
from app.public_view.projections import PublicReportContent, read_public_report, public_source_name, utc_date

router = APIRouter(prefix='/api/public/v1', tags=['public'])


class PublicActivity(BaseModel):
    date: datetime
    source_name: str
    status: Literal['COMPLETED', 'FAILED']
    response_bytes: int | None = Field(default=None, ge=0)
    text_characters: int | None = Field(default=None, ge=0)


class ActivityPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[PublicActivity]


class PublishedReport(BaseModel):
    id: uuid.UUID
    published_at: datetime
    content: PublicReportContent


class ReportPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[PublishedReport]


def published(row: ReportPublication) -> PublishedReport:
    return PublishedReport(id=row.id, published_at=utc_date(row.published_at),
                           content=read_public_report(row.payload))


@router.get('/activity', response_model=ActivityPage)
def activity(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=10000),
             db: Session = Depends(get_session)):
    protected = select(ClassificationResult.id).where(
        ClassificationResult.observation_id == SourceObservation.id,
        ClassificationResult.category == 'SUSPECTED_CHILD_EXPLOITATION').exists()
    query = (select(CrawlJob.finished_at, CrawlJob.created_at, CrawlJob.status, OnionSource.name,
                    SourceObservation.response_bytes, SourceObservation.text_length)
             .select_from(CrawlJob).join(OnionSource, OnionSource.id == CrawlJob.source_id)
             .outerjoin(SourceObservation, SourceObservation.job_id == CrawlJob.id)
             .where(CrawlJob.status.in_(['COMPLETED', 'FAILED']),
                    OnionSource.deleted_at.is_(None), OnionSource.is_active.is_(True),
                    OnionSource.approved_for_collection.is_(True), ~protected))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(func.coalesce(CrawlJob.finished_at, CrawlJob.created_at).desc(), CrawlJob.id.desc())
                      .limit(limit).offset(offset)).all()
    return ActivityPage(total=total, limit=limit, offset=offset, items=[PublicActivity(
        date=utc_date(finished or created), source_name=public_source_name(name),
        status=status, response_bytes=received if status == 'COMPLETED' else None,
        text_characters=length if status == 'COMPLETED' else None,
    ) for finished, created, status, name, received, length in rows])


@router.get('/reports', response_model=ReportPage)
def reports(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=10000),
            db: Session = Depends(get_session)):
    clause = ReportPublication.is_public.is_(True)
    total = db.scalar(select(func.count()).select_from(ReportPublication).where(clause)) or 0
    rows = db.scalars(select(ReportPublication).where(clause).order_by(
        ReportPublication.published_at.desc(), ReportPublication.id.desc()).limit(limit).offset(offset)).all()
    return ReportPage(total=total, limit=limit, offset=offset, items=[published(row) for row in rows])


@router.get('/reports/{publication_id}', response_model=PublishedReport)
def report(publication_id: uuid.UUID, db: Session = Depends(get_session)):
    row = db.scalar(select(ReportPublication).where(ReportPublication.id == publication_id,
                                                  ReportPublication.is_public.is_(True)))
    if row is None:
        raise HTTPException(404, 'Public report not found')
    return published(row)
